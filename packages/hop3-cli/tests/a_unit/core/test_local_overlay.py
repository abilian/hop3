# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the .hop3-local.toml reader/writer (ADR 042 §File layout)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from hop3_cli.core.local_overlay import (
    LOCAL_OVERLAY_FILENAME,
    LocalOverlay,
    find_overlay_file,
    read_overlay,
    write_overlay,
)

if TYPE_CHECKING:
    from pathlib import Path


# ---- read_overlay ---------------------------------------------------------


def test_read_overlay_missing_file_returns_empty(tmp_path: Path) -> None:
    """No overlay file in CWD or ancestors → empty data, None path."""
    overlay = read_overlay(cwd=tmp_path, home=tmp_path)
    assert overlay.path is None
    assert overlay.data == {}
    assert overlay.current_context is None


def test_read_overlay_finds_in_cwd(tmp_path: Path) -> None:
    """A .hop3-local.toml in CWD is read (legacy [current] key — read-tolerance)."""
    (tmp_path / LOCAL_OVERLAY_FILENAME).write_text('[current]\ncontext = "dev"\n')
    overlay = read_overlay(cwd=tmp_path, home=tmp_path)
    assert overlay.path == tmp_path / LOCAL_OVERLAY_FILENAME
    assert overlay.current_context == "dev"


def test_read_overlay_canonical_local_key(tmp_path: Path) -> None:
    """
    ADR 042 r2: the canonical key is [local].context; it wins over a stale
    legacy [current] if both are present.
    """
    (tmp_path / LOCAL_OVERLAY_FILENAME).write_text(
        '[current]\ncontext = "stale"\n[local]\ncontext = "prod"\n'
    )
    overlay = read_overlay(cwd=tmp_path, home=tmp_path)
    assert overlay.current_context == "prod"


def test_read_overlay_walks_up_to_home(tmp_path: Path) -> None:
    """The overlay is found in an ancestor of CWD."""
    (tmp_path / LOCAL_OVERLAY_FILENAME).write_text('[current]\ncontext = "prod"\n')
    sub = tmp_path / "src" / "deep"
    sub.mkdir(parents=True)
    overlay = read_overlay(cwd=sub, home=tmp_path)
    assert overlay.current_context == "prod"


def test_read_overlay_unparseable_returns_empty_data_keeps_path(
    tmp_path: Path,
) -> None:
    """
    A broken TOML file yields empty data but the path is preserved.

    Lets callers distinguish 'no overlay' from 'broken overlay' if they
    need to (e.g., to warn the operator about the parse failure).
    """
    overlay_path = tmp_path / LOCAL_OVERLAY_FILENAME
    overlay_path.write_text("not valid toml [[[")
    overlay = read_overlay(cwd=tmp_path, home=tmp_path)
    assert overlay.path == overlay_path
    assert overlay.data == {}
    assert overlay.current_context is None


def test_current_context_handles_missing_section(tmp_path: Path) -> None:
    """An overlay without [current] still parses; current_context is None."""
    (tmp_path / LOCAL_OVERLAY_FILENAME).write_text('[other]\nkey = "value"\n')
    overlay = read_overlay(cwd=tmp_path, home=tmp_path)
    assert overlay.current_context is None


def test_current_context_handles_empty_string(tmp_path: Path) -> None:
    """An empty / whitespace-only context value is treated as unset."""
    (tmp_path / LOCAL_OVERLAY_FILENAME).write_text('[current]\ncontext = "   "\n')
    overlay = read_overlay(cwd=tmp_path, home=tmp_path)
    assert overlay.current_context is None


def test_local_overlay_dataclass_is_frozen() -> None:
    from dataclasses import FrozenInstanceError  # ruff:ignore[import-outside-top-level]

    o = LocalOverlay(path=None, data={})
    with pytest.raises(FrozenInstanceError):
        setattr(o, "path", "mutated")  # ruff:ignore[set-attr-with-constant]  # frozen: assignment must raise


# ---- write_overlay ------------------------------------------------------


def test_write_overlay_creates_file(tmp_path: Path) -> None:
    """Writing when no overlay exists creates one at CWD."""
    path = write_overlay(
        {"current": {"context": "dev"}},
        cwd=tmp_path,
        home=tmp_path,
        ensure_gitignore=False,
    )
    assert path == tmp_path / LOCAL_OVERLAY_FILENAME
    assert path.is_file()
    overlay = read_overlay(cwd=tmp_path, home=tmp_path)
    assert overlay.current_context == "dev"


def test_write_overlay_overwrites_existing_key(tmp_path: Path) -> None:
    """A second write overwrites the previous context value."""
    write_overlay(
        {"current": {"context": "dev"}},
        cwd=tmp_path,
        home=tmp_path,
        ensure_gitignore=False,
    )
    write_overlay(
        {"current": {"context": "prod"}},
        cwd=tmp_path,
        home=tmp_path,
        ensure_gitignore=False,
    )
    overlay = read_overlay(cwd=tmp_path, home=tmp_path)
    assert overlay.current_context == "prod"


def test_write_overlay_preserves_sibling_keys(tmp_path: Path) -> None:
    """Writing one key under [current] keeps other [current] keys."""
    overlay_path = tmp_path / LOCAL_OVERLAY_FILENAME
    overlay_path.write_text('[current]\ncontext = "dev"\napp = "myapp-dev"\n')
    write_overlay(
        {"current": {"context": "prod"}},
        cwd=tmp_path,
        home=tmp_path,
        ensure_gitignore=False,
    )
    overlay = read_overlay(cwd=tmp_path, home=tmp_path)
    assert overlay.current_context == "prod"
    # Sibling key under [current] survives the per-section merge.
    assert overlay.data["current"]["app"] == "myapp-dev"


def test_write_overlay_writes_to_existing_ancestor(tmp_path: Path) -> None:
    """When an overlay already exists in an ancestor, writes target the same path."""
    (tmp_path / LOCAL_OVERLAY_FILENAME).write_text('[current]\ncontext = "dev"\n')
    sub = tmp_path / "src"
    sub.mkdir()
    written = write_overlay(
        {"current": {"context": "prod"}},
        cwd=sub,
        home=tmp_path,
        ensure_gitignore=False,
    )
    # The write goes to the ancestor file, not a new one at sub/.
    assert written == tmp_path / LOCAL_OVERLAY_FILENAME
    assert not (sub / LOCAL_OVERLAY_FILENAME).exists()


def test_write_overlay_appends_to_gitignore(tmp_path: Path) -> None:
    """When .gitignore exists and doesn't list the overlay, append it."""
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("node_modules/\n.venv/\n")
    write_overlay(
        {"current": {"context": "dev"}},
        cwd=tmp_path,
        home=tmp_path,
        ensure_gitignore=True,
    )
    content = gitignore.read_text()
    assert LOCAL_OVERLAY_FILENAME in content
    # Existing entries preserved.
    assert "node_modules/" in content


def test_write_overlay_does_not_duplicate_gitignore_entry(
    tmp_path: Path,
) -> None:
    """If .gitignore already lists the overlay, we don't add it again."""
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text(f".venv/\n{LOCAL_OVERLAY_FILENAME}\n")
    write_overlay(
        {"current": {"context": "dev"}},
        cwd=tmp_path,
        home=tmp_path,
        ensure_gitignore=True,
    )
    # Still just one occurrence.
    assert gitignore.read_text().count(LOCAL_OVERLAY_FILENAME) == 1


def test_write_overlay_recognises_slashed_gitignore_entry(
    tmp_path: Path,
) -> None:
    """`/` prefix in .gitignore (root-anchored) also counts as already-ignored."""
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text(f"/{LOCAL_OVERLAY_FILENAME}\n")
    write_overlay(
        {"current": {"context": "dev"}},
        cwd=tmp_path,
        home=tmp_path,
        ensure_gitignore=True,
    )
    # No duplicate added.
    content = gitignore.read_text()
    assert content.count(LOCAL_OVERLAY_FILENAME) == 1


def test_write_overlay_no_gitignore_outside_git_skipped(tmp_path: Path) -> None:
    """
    When .gitignore doesn't exist AND we're not in a git repo, do nothing.

    The .gitignore is the operator's choice; we don't auto-create it
    unless they've already committed to git (which is what the presence
    of .git/ signals).
    """
    write_overlay(
        {"current": {"context": "dev"}},
        cwd=tmp_path,
        home=tmp_path,
        ensure_gitignore=True,
    )
    assert not (tmp_path / ".gitignore").exists()


def test_write_overlay_creates_gitignore_inside_git_repo(
    tmp_path: Path,
) -> None:
    """
    Inside a git repo with no .gitignore, we create one with our line.

    This is the case the feature exists to handle: a fresh git init that
    hasn't set up ignores yet but where committing .hop3-local.toml
    would leak per-checkout state.
    """
    (tmp_path / ".git").mkdir()  # Simulate `git init`
    write_overlay(
        {"current": {"context": "dev"}},
        cwd=tmp_path,
        home=tmp_path,
        ensure_gitignore=True,
    )
    gitignore = tmp_path / ".gitignore"
    assert gitignore.is_file()
    content = gitignore.read_text()
    assert LOCAL_OVERLAY_FILENAME in content
    # Includes the header comment so operators see why we created the file.
    assert "ADR 042" in content


def test_write_overlay_creates_gitignore_at_git_root_not_cwd(
    tmp_path: Path,
) -> None:
    """A new .gitignore is created at the GIT ROOT, not at the CWD."""
    (tmp_path / ".git").mkdir()
    sub = tmp_path / "subproject"
    sub.mkdir()
    write_overlay(
        {"current": {"context": "dev"}},
        cwd=sub,
        home=tmp_path,
        ensure_gitignore=True,
    )
    # At git root, not in the subdirectory.
    assert (tmp_path / ".gitignore").is_file()
    assert not (sub / ".gitignore").exists()


def test_write_overlay_ensure_gitignore_false_skips(tmp_path: Path) -> None:
    """With ensure_gitignore=False, .gitignore is left untouched."""
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text(".venv/\n")
    write_overlay(
        {"current": {"context": "dev"}},
        cwd=tmp_path,
        home=tmp_path,
        ensure_gitignore=False,
    )
    assert LOCAL_OVERLAY_FILENAME not in gitignore.read_text()


def test_write_overlay_atomic_on_existing_file(tmp_path: Path) -> None:
    """The write replaces the file atomically — no partial file on disk."""
    overlay_path = tmp_path / LOCAL_OVERLAY_FILENAME
    overlay_path.write_text('[current]\ncontext = "original"\n')
    write_overlay(
        {"current": {"context": "updated"}},
        cwd=tmp_path,
        home=tmp_path,
        ensure_gitignore=False,
    )
    # No tmpfiles left behind.
    leftovers = [
        p
        for p in tmp_path.iterdir()
        if p.name.startswith(f".{LOCAL_OVERLAY_FILENAME}.")
    ]
    assert leftovers == []
    overlay = read_overlay(cwd=tmp_path, home=tmp_path)
    assert overlay.current_context == "updated"


# ---- find_overlay_file --------------------------------------------------


def test_find_overlay_file_at_cwd(tmp_path: Path) -> None:
    (tmp_path / LOCAL_OVERLAY_FILENAME).write_text("[current]\n")
    assert find_overlay_file(tmp_path, tmp_path) == (tmp_path / LOCAL_OVERLAY_FILENAME)


def test_find_overlay_file_walks_up(tmp_path: Path) -> None:
    (tmp_path / LOCAL_OVERLAY_FILENAME).write_text("[current]\n")
    sub = tmp_path / "a" / "b" / "c"
    sub.mkdir(parents=True)
    assert find_overlay_file(sub, tmp_path) == (tmp_path / LOCAL_OVERLAY_FILENAME)


def test_find_overlay_file_stops_at_home(tmp_path: Path) -> None:
    """Search must not escape ``home`` (avoid reaching into /etc etc.)."""
    # Build a directory hierarchy where the overlay is ABOVE home.
    outer = tmp_path
    home = outer / "home"
    home.mkdir()
    cwd = home / "project"
    cwd.mkdir()
    (outer / LOCAL_OVERLAY_FILENAME).write_text("[current]\n")
    assert find_overlay_file(cwd, home) is None
