# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Git source fetch: a ref (branch/tag/sha) checks out to its own clean worktree.

This is the apps half of the §A composition — a source repo fetched at a chosen
ref, independent of the platform ref. We assert the right tree lands per ref and
that two refs coexist as separate worktrees (the composition needs both at once).
"""

from __future__ import annotations

import subprocess

import pytest

from hop3_testlab import sources


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _make_origin(tmp_path):
    """A tiny origin repo: tag v1 (=main) on commit 1, branch devel on commit 2."""
    origin = tmp_path / "origin"
    origin.mkdir()
    _git("init", "-b", "main", cwd=origin)
    _git("config", "user.email", "t@example.com", cwd=origin)
    _git("config", "user.name", "Test", cwd=origin)
    (origin / "marker.txt").write_text("main-v1\n")
    _git("add", ".", cwd=origin)
    _git("commit", "-m", "first", cwd=origin)
    _git("tag", "v1", cwd=origin)
    _git("checkout", "-b", "devel", cwd=origin)
    (origin / "marker.txt").write_text("devel-v2\n")
    _git("commit", "-am", "devel change", cwd=origin)
    devel_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=origin,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    _git("checkout", "main", cwd=origin)
    return origin, devel_sha


@pytest.fixture
def source(tmp_path, monkeypatch):
    origin, devel_sha = _make_origin(tmp_path)
    monkeypatch.setattr(sources, "SOURCES_ROOT", tmp_path / "cache")
    monkeypatch.setattr(sources, "WORKSPACES_ROOT", tmp_path / "ws")
    return sources.Source("repo", str(origin)), devel_sha


def test_fetch_resolves_branch_tag_and_sha(source):
    src, devel_sha = source
    assert (src.fetch("main") / "marker.txt").read_text() == "main-v1\n"
    assert (src.fetch("v1") / "marker.txt").read_text() == "main-v1\n"  # tag
    assert (src.fetch("devel") / "marker.txt").read_text() == "devel-v2\n"
    assert (src.fetch(devel_sha) / "marker.txt").read_text() == "devel-v2\n"  # sha


def test_refs_coexist_as_separate_worktrees(source):
    """Composition needs two refs of one repo checked out at the same time."""
    src, _ = source
    ws_main = src.fetch("main")
    ws_devel = src.fetch("devel")
    assert ws_main != ws_devel
    # Fetching devel must not disturb main's already-laid-down worktree.
    assert (ws_main / "marker.txt").read_text() == "main-v1\n"
    assert (ws_devel / "marker.txt").read_text() == "devel-v2\n"


def test_refetch_is_clean(source):
    """A re-fetch of the same ref leaves a clean tree (no stray local files)."""
    src, _ = source
    ws = src.fetch("main")
    (ws / "stray.txt").write_text("leftover\n")
    ws2 = src.fetch("main")
    assert ws2 == ws
    assert not (ws2 / "stray.txt").exists()


def test_unknown_ref_fails_loud(source):
    src, _ = source
    with pytest.raises(RuntimeError, match="can't resolve ref"):
        src.fetch("no-such-ref")


def test_is_allowed_source_url():
    ok = sources.is_allowed_source_url
    assert ok("https://github.com/abilian/hop3.git")
    assert ok("git@github.com:abilian/hop3.git")  # scp-like ssh
    assert ok("ssh://git@host/repo.git")
    assert ok("/abs/local/repo")  # absolute local path (the e2e uses this)
    # Rejected: git transport helpers, option injection, junk.
    assert not ok("ext::sh -c 'evil'")
    assert not ok("fd::7")
    assert not ok("-oProxyCommand=evil")
    assert not ok("")
    assert not ok("relative/path")
