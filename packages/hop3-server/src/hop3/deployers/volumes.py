# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Realize declarative `[[volumes]]` (ADR 046 §2).

Every deploy replaces `src/`. A volume is a directory outside it, linked into
the fresh tree at ``target``, so what the app writes there outlives the deploy:

- ``persist`` keeps its contents, under `<app>/volumes/<name>/`, and is backed
  up. An empty one is seeded once: from what the app wrote at ``target`` in the
  tree this deploy replaces, else from what the build left there.
- ``scratch`` is writable and disposable, under `<app>/scratch/<name>/`: emptied
  on every deploy, refilled from what the build left at ``target``, never
  backed up. It is for caches a newer version must not inherit.

Volumes are linked after the build, before the app starts: a build that
unpacks the application moves directories into place, and a link in the way
breaks it. The tree a deploy replaces is kept aside (`retire_source_tree`)
until then (`drop_previous_source`). Without it, declaring a volume
for data an app already writes into `src/` would delete that data on the very
deploy that declares it.

``tmpfs`` and ``bind`` need privileged mounts (rootd) and are not implemented
yet — they fail the deploy loudly rather than silently doing nothing.
"""

from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING, Any

from hop3.config import HOP3_USER
from hop3.lib import log
from hop3.lib.path import is_confined_to
from hop3.lib.util import robust_rmtree

if TYPE_CHECKING:
    from pathlib import Path

    from hop3.orm.app import App

#: Volume types this module realizes; the schema also accepts tmpfs and bind.
IMPLEMENTED_TYPES = ("persist", "scratch")


def previous_source_path(app: App) -> Path:
    """Where the tree a deploy replaces waits until the build is done."""
    return app.app_path / "src.previous"


def retire_source_tree(app: App) -> None:
    """
    Move `src/` aside before a deploy replaces it.

    If a tree is already set aside, the deploy that set it aside failed before
    its build was done, so the app never ran from the tree now in `src/`:
    nothing in it was written by the app. That tree goes, and the older
    one stays, since it is the one the app last ran from.
    """
    previous = previous_source_path(app)
    if previous.exists():
        robust_rmtree(app.src_path)
        return
    if app.src_path.exists():
        app.src_path.rename(previous)


def drop_previous_source(app: App) -> None:
    """Delete the tree `retire_source_tree` kept, once volumes are relinked."""
    robust_rmtree(previous_source_path(app))


def realize_volumes(app: App, volumes: list[dict[str, Any]]) -> None:
    """Link each declared volume into the app's source tree (ADR 046 §2)."""
    for vol in volumes:
        name = vol["name"]
        target = vol["target"]
        vtype = vol.get("type", "persist")
        mode = vol.get("mode")

        match vtype:
            case "persist":
                storage = _storage_dir(app.volumes_path / name, name, mode)
                linked = _link(app, name, target, storage, seed_from_previous=True)
                where = f"volumes/{name}"
            case "scratch":
                storage = app.scratch_path / name
                if not _points_to(app.src_path / target, storage):
                    # A new tree: start from what it ships, not from what the
                    # previous version wrote. A deploy that keeps the tree (a
                    # config change) keeps the scratch, whose shipped content
                    # now lives nowhere else.
                    robust_rmtree(storage)
                _storage_dir(storage, name, mode)
                linked = _link(app, name, target, storage, seed_from_previous=False)
                where = f"scratch/{name} (reset on every deploy)"
            case _:
                msg = (
                    f"[[volumes]] {name!r}: type {vtype!r} is not implemented yet "
                    f"(ADR 046); only {' and '.join(IMPLEMENTED_TYPES)} are."
                )
                raise ValueError(msg)
        if linked:
            log(f"  Volume {name!r}: '{target}' -> {where}", level=1, fg="green")


def _storage_dir(path: Path, name: str, mode: str | None) -> Path:
    """Create a volume's storage, owned by the user the app runs as."""
    path.mkdir(parents=True, exist_ok=True)

    # The volume must be owned and writable by the user the app runs as (hop3),
    # not by whoever ran the deploy. When the deploy runs as root, hand it back
    # to HOP3_USER so the app process isn't left with an unwritable volume.
    if os.geteuid() == 0:
        # A failure stops the deploy: it was logged and the app started with a
        # volume it could not write.
        try:
            shutil.chown(path, user=HOP3_USER, group=HOP3_USER)
        except (LookupError, PermissionError) as e:
            msg = (
                f"[[volumes]] {name!r}: cannot give {path} to {HOP3_USER}, so the "
                f"app could not write to it: {e}"
            )
            raise ValueError(msg) from e
    if mode is not None:
        path.chmod(int(mode, 8))
    return path


def _link(
    app: App, name: str, target: str, storage: Path, *, seed_from_previous: bool
) -> bool:
    """
    Symlink ``src/<target>`` to ``storage``, seeding ``storage`` if empty.

    False when the link was already in place, True when it was made.
    """
    src_root = app.src_path
    link_path = src_root / target

    # Defense in depth: the link must stay within src/. The schema already
    # rejects absolute paths and '..', but recheck in case validation was
    # bypassed (HOP3_SKIP_CONFIG_VALIDATION). realpath both sides — a lexical
    # check passes an in-tree symlink (src/data -> /etc) that this function
    # would then seed from and replace.
    if not is_confined_to(link_path.parent, src_root):
        msg = f"[[volumes]] {name!r}: target {target!r} escapes the app source tree."
        raise ValueError(msg)

    if link_path.is_symlink():
        if _points_to(link_path, storage):
            return False  # already linked correctly
        link_path.unlink()  # stale/incorrect link — replace it
    elif link_path.exists() and not link_path.is_dir():
        msg = (
            f"[[volumes]] {name!r}: target {target!r} exists as a file; "
            "volume targets must be directories."
        )
        raise ValueError(msg)

    if not any(storage.iterdir()):
        previous = _previous_content(app, target) if seed_from_previous else None
        if previous is not None:
            _move_contents(previous, storage)
            log(
                f"  Volume {name!r}: kept what the app had written at '{target}' "
                "before this deploy",
                level=0,
                fg="yellow",
            )
        elif link_path.is_dir():
            _move_contents(link_path, storage)
    # Whatever the new source ships at the target is either in the storage now
    # or superseded by it: the link is the single source of truth.
    robust_rmtree(link_path)

    link_path.parent.mkdir(parents=True, exist_ok=True)
    # Relative link so no absolute host path leaks into copied/archived trees;
    # it still resolves at runtime (the OS resolves it from the link's location).
    link_path.symlink_to(os.path.relpath(storage, link_path.parent))
    return True


def _previous_content(app: App, target: str) -> Path | None:
    """
    The replaced tree's real, non-empty directory at ``target``, if any.

    A link there means the path was already a volume, whose storage is not
    this one's to take. The confinement check is realpath-based, so a link the
    app planted higher up (``storage -> /etc``) is not followed out of the tree.
    """
    root = previous_source_path(app)
    path = root / target
    if path.is_symlink() or not path.is_dir():
        return None
    if not is_confined_to(path, root):
        return None
    if not any(path.iterdir()):
        return None
    return path


def _move_contents(source: Path, dest: Path) -> None:
    for item in source.iterdir():
        shutil.move(str(item), str(dest / item.name))


def _points_to(link: Path, target_dir: Path) -> bool:
    """True if ``link`` already resolves to ``target_dir``."""
    try:
        return link.resolve() == target_dir.resolve()
    except OSError:
        return False
