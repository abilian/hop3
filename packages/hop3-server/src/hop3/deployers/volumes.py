# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Realize declarative `[[volumes]]` persistence (ADR 046 §2).

A ``persist`` volume is a directory under the app's data root
(`<app>/volumes/<name>/`) symlinked into the freshly-extracted source tree at
``target``. Because the storage lives *outside* `src/`, it survives the redeploy
sequence (stop → wipe & re-extract `src/` → `git clean`); the link is simply
re-established on every deploy. The first deploy seeds an empty volume from any
content the app shipped at ``target``, so default data isn't lost.

``tmpfs`` and ``bind`` need privileged mounts (rootd) and are not implemented
yet — they fail the deploy loudly rather than silently doing nothing.
"""

from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING, Any

from hop3.config import HOP3_USER
from hop3.lib import log

if TYPE_CHECKING:
    from pathlib import Path

    from hop3.orm.app import App


def realize_volumes(app: App, volumes: list[dict[str, Any]]) -> None:
    """Link each declared volume into the app's source tree (ADR 046 §2)."""
    if not volumes:
        return

    for vol in volumes:
        name = vol["name"]
        target = vol["target"]
        vtype = vol.get("type", "persist")

        if vtype != "persist":
            msg = (
                f"[[volumes]] {name!r}: type {vtype!r} is not implemented yet "
                "(ADR 046); only 'persist' is supported."
            )
            raise ValueError(msg)

        _realize_persist_volume(app, name, target, vol.get("mode"))
        log(
            f"  Volume {name!r}: persisting '{target}' -> volumes/{name}",
            level=1,
            fg="green",
        )


def _realize_persist_volume(
    app: App, name: str, target: str, mode: str | None = None
) -> None:
    """Symlink ``src/<target>`` to the app's persistent ``volumes/<name>`` dir."""
    volume_dir = app.volumes_path / name
    volume_dir.mkdir(parents=True, exist_ok=True)

    # The volume must be owned and writable by the user the app runs as (hop3),
    # not by whoever ran the deploy. When the deploy runs as root, hand it back
    # to HOP3_USER so the app process isn't left with an unwritable volume.
    if os.geteuid() == 0:
        try:
            shutil.chown(volume_dir, user=HOP3_USER, group=HOP3_USER)
        except (LookupError, PermissionError) as e:
            log(f"  Volume {name!r}: could not chown to {HOP3_USER}: {e}", level=1)
    if mode is not None:
        volume_dir.chmod(int(mode, 8))

    src_root = app.src_path
    link_path = src_root / target

    # Defense in depth: the link must stay within src/. The schema already
    # rejects absolute paths and '..', but recheck against the normalized path
    # in case validation was bypassed (HOP3_SKIP_CONFIG_VALIDATION).
    norm = os.path.normpath(link_path)
    if norm != str(src_root) and not norm.startswith(str(src_root) + os.sep):
        msg = f"[[volumes]] {name!r}: target {target!r} escapes the app source tree."
        raise ValueError(msg)

    if link_path.is_symlink():
        if _points_to(link_path, volume_dir):
            return  # already linked correctly
        link_path.unlink()  # stale/incorrect link — replace it
    elif link_path.exists():
        if not link_path.is_dir():
            msg = (
                f"[[volumes]] {name!r}: target {target!r} exists as a file; "
                "volume targets must be directories."
            )
            raise ValueError(msg)
        # Extracted content at the target: seed the volume from it once (only
        # when the volume is still empty), then replace it with the link so the
        # persistent dir becomes the single source of truth.
        if not any(volume_dir.iterdir()):
            for item in link_path.iterdir():
                shutil.move(str(item), str(volume_dir / item.name))
        shutil.rmtree(link_path)

    link_path.parent.mkdir(parents=True, exist_ok=True)
    # Relative link so no absolute host path leaks into copied/archived trees;
    # it still resolves at runtime (the OS resolves it from the link's location).
    link_path.symlink_to(os.path.relpath(volume_dir, link_path.parent))


def _points_to(link: Path, target_dir: Path) -> bool:
    """True if ``link`` already resolves to ``target_dir``."""
    try:
        return link.resolve() == target_dir.resolve()
    except OSError:
        return False
