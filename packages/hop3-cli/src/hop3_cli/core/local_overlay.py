# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Reader and writer for ``.hop3-local.toml`` (ADR 042 §File layout).

The local overlay is a per-checkout, gitignored TOML file that records
which project context is currently selected. It lives at the project root
alongside ``hop3.toml`` and is the sole carrier for "which context is
current" — the legacy single-line ``.hop3-context`` file was retired in
ADR 042 Step 7.

Shape::

    [current]
    context = "dev"

The writer is atomic (mkstemp + ``os.replace``) and automatically appends
``.hop3-local.toml`` to ``.gitignore`` when it isn't already ignored, so
operators don't accidentally commit their per-checkout state.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import toml
import tomllib

LOCAL_OVERLAY_FILENAME = ".hop3-local.toml"
GITIGNORE_FILENAME = ".gitignore"


@dataclass(frozen=True)
class LocalOverlay:
    """Materialised view of the nearest ``.hop3-local.toml``.

    Attributes:
        path: The discovered file path, or None when no overlay exists.
        data: The parsed TOML data, or empty dict when no overlay exists.
        current_context: Shortcut for ``data['current']['context']`` (or
            None when the field isn't set).
    """

    path: Path | None
    data: dict[str, Any]

    @property
    def current_context(self) -> str | None:
        """Return ``[current].context`` if set and non-empty, else None."""
        current = self.data.get("current")
        if not isinstance(current, dict):
            return None
        value = current.get("context")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None


def find_overlay_file(cwd: Path, home: Path) -> Path | None:
    """Walk upward from ``cwd`` looking for ``.hop3-local.toml``.

    Search stops at ``home`` (inclusive), matching the existing
    ``_search_dotfile`` convention in ``resolution.py``. Returns the
    first match, or None.
    """
    current = cwd.resolve()
    stop_at = home.resolve()
    while True:
        candidate = current / LOCAL_OVERLAY_FILENAME
        if candidate.is_file():
            return candidate
        if current in {stop_at, current.parent}:
            break
        current = current.parent
    return None


def read_overlay(cwd: Path | None = None, home: Path | None = None) -> LocalOverlay:
    """Return the materialised overlay for the nearest ``.hop3-local.toml``.

    On parse error, returns an overlay with ``data == {}`` and the
    discovered path preserved. (The caller can distinguish "no overlay"
    from "broken overlay" via ``overlay.path is not None`` if needed.)
    """
    cwd = cwd or Path.cwd()
    home = home or Path.home()

    path = find_overlay_file(cwd, home)
    if path is None:
        return LocalOverlay(path=None, data={})
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return LocalOverlay(path=path, data={})
    return LocalOverlay(path=path, data=data)


def write_overlay(
    updates: dict[str, Any],
    *,
    cwd: Path | None = None,
    home: Path | None = None,
    ensure_gitignore: bool = True,
) -> Path:
    """Merge ``updates`` into the nearest overlay and write it back atomically.

    The write target is determined by:
    1. The path returned by ``find_overlay_file`` (if an overlay already
       exists in CWD or an ancestor — we keep writing to the same place).
    2. ``cwd / LOCAL_OVERLAY_FILENAME`` otherwise.

    ``updates`` is a dict whose values are merged into the existing data
    one level deep. So passing ``{"current": {"context": "dev"}}`` adds
    or overwrites only that key under ``[current]`` while leaving other
    sub-keys untouched.

    Args:
        updates: Top-level table updates to merge.
        cwd: Directory to start looking from (defaults to ``Path.cwd()``).
        home: User home directory (defaults to ``Path.home()``).
        ensure_gitignore: If True (default), append
            ``.hop3-local.toml`` to ``.gitignore`` when not already
            present. Set False for tests that don't want to mutate
            ``.gitignore``.

    Returns:
        The path written.
    """
    cwd = cwd or Path.cwd()
    home = home or Path.home()

    target = find_overlay_file(cwd, home) or (cwd / LOCAL_OVERLAY_FILENAME)

    # Start from the existing data so per-section merges preserve siblings.
    overlay = read_overlay(cwd=target.parent, home=home)
    merged = _deep_merge(overlay.data, updates)

    atomic_write_toml(target, merged)

    if ensure_gitignore:
        _ensure_gitignored(target)

    return target


def _deep_merge(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    """One-level-deep dict merge.

    Top-level keys whose values in both dicts are dicts get their inner
    items merged; everything else is replaced wholesale. Returns a new
    dict; neither input is mutated.
    """
    result = dict(base)
    for k, v in updates.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            inner = dict(result[k])
            inner.update(v)
            result[k] = inner
        else:
            result[k] = v
    return result


def atomic_write_toml(target: Path, data: dict[str, Any]) -> None:
    """Write ``data`` as TOML to ``target`` atomically and durably.

    Uses the standard tmpfile-then-rename pattern: write to a sibling
    temp file, fsync its contents, atomically rename into place, then
    fsync the parent directory so the rename itself survives power loss.

    Guarantees:
    - **Atomic against concurrent readers** — readers see either the
      old file or the new file, never a half-written one.
    - **Durable against power loss after this call returns** — the
      parent-directory fsync ensures the new dirent is on stable
      storage. (Some filesystems silently no-op the dir fsync, in
      which case durability is best-effort; the call is still safe.)

    Shared by the overlay writer and the project ``hop3.toml`` writers
    so they have the same durability profile.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            toml.dump(data, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise

    # fsync the parent directory so the rename is durable. Some
    # filesystems (notably certain CI tmpfs / NFS configurations)
    # reject dir-fsync; treat those as a soft failure.
    _fsync_dir(target.parent)


# Back-compat alias for any in-tree callers that imported the old name.
_atomic_write_toml = atomic_write_toml


def _fsync_dir(directory: Path) -> None:
    """Best-effort fsync of ``directory``.

    Required after ``os.replace`` so the rename is durable. Silently
    swallows OSError because some filesystems reject directory fsync;
    durability is the goal, not a hard requirement on every host.
    """
    try:
        dir_fd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        with contextlib.suppress(OSError):
            os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _ensure_gitignored(overlay_path: Path) -> None:
    """Append ``.hop3-local.toml`` to ``.gitignore`` when missing.

    Three behaviors based on what we find walking upward:

    1. Ancestor has a ``.gitignore`` already → append our line if missing.
    2. Ancestor has a ``.git/`` directory but no ``.gitignore`` → create
       a new ``.gitignore`` at the git root with our line. This is the
       case the feature exists to handle: a fresh ``git init`` repo
       that hasn't set up ignores yet but where committing
       ``.hop3-local.toml`` would leak per-checkout state.
    3. Neither found (not inside a git repo) → do nothing.

    Idempotent: existing entries are detected via line-exact match
    (with optional leading slash, since ``.hop3-local.toml`` and
    ``/.hop3-local.toml`` both correctly ignore the file at the
    repo root).
    """
    gitignore, git_root = _find_gitignore_or_git_root(overlay_path.parent)

    if gitignore is not None:
        _append_to_gitignore(gitignore)
        return

    if git_root is not None:
        # Inside a git repo, no .gitignore yet — create one at the
        # git root with a focused header comment so operators see why
        # we wrote it.
        new_gitignore = git_root / GITIGNORE_FILENAME
        content = (
            "# Created by `hop3 context use` (or similar) to keep per-checkout\n"
            "# state out of version control. See ADR 042 (Hop3 CLI context model).\n"
            f"{LOCAL_OVERLAY_FILENAME}\n"
        )
        with contextlib.suppress(OSError):
            new_gitignore.write_text(content, encoding="utf-8")


def _append_to_gitignore(gitignore: Path) -> None:
    """Idempotently append ``.hop3-local.toml`` to an existing .gitignore."""
    try:
        existing = gitignore.read_text(encoding="utf-8")
    except OSError:
        return

    if _gitignore_already_covers(existing, LOCAL_OVERLAY_FILENAME):
        return

    # Append, with a leading newline if the file doesn't end in one.
    suffix = "" if existing.endswith("\n") else "\n"
    new_content = f"{existing}{suffix}{LOCAL_OVERLAY_FILENAME}\n"
    with contextlib.suppress(OSError):
        gitignore.write_text(new_content, encoding="utf-8")


def _find_gitignore_or_git_root(
    start: Path,
) -> tuple[Path | None, Path | None]:
    """Walk up from ``start`` looking for ``.gitignore`` and ``.git/``.

    Returns ``(gitignore_path, git_root_path)``. Both are populated when
    both are found at different ancestor levels; either may be None.
    Stops at the filesystem root.

    The two are looked for together so a single walk covers both cases
    (existing .gitignore wins; otherwise we know whether we're inside a
    git repo and can create one).
    """
    current = start.resolve()
    gitignore_path: Path | None = None
    git_root_path: Path | None = None
    while True:
        if gitignore_path is None:
            candidate = current / GITIGNORE_FILENAME
            if candidate.is_file():
                gitignore_path = candidate
        if git_root_path is None and (current / ".git").is_dir():
            git_root_path = current
        # Stop early if both found.
        if gitignore_path is not None and git_root_path is not None:
            break
        if current == current.parent:
            break
        current = current.parent
    return gitignore_path, git_root_path


def _gitignore_already_covers(content: str, filename: str) -> bool:
    """True iff ``content`` already has a line that ignores ``filename``.

    Recognises the two common idioms:
    - ``.hop3-local.toml`` (matches anywhere by default)
    - ``/.hop3-local.toml`` (matches only at repo root)
    Comments and blank lines are skipped.
    """
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line in {filename, f"/{filename}"}:
            return True
    return False
