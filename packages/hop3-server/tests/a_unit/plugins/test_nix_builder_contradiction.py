# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Tests for NixBuilder's contradiction check.

When both an explicit hop3.nix file AND a [nix].template section in
hop3.toml are present, the builder must abort with an actionable
error rather than silently picking one.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from hop3.core.protocols import BuildContext
from hop3.lib import Abort
from hop3.plugins.build.nix.builder import NixBuilder

if TYPE_CHECKING:
    from pathlib import Path


def _make_context(source_path: Path, app_config: dict) -> BuildContext:
    return BuildContext(
        app_name="testapp",
        source_path=source_path,
        app_config=app_config,
    )


def test_accept_with_only_hop3_nix(tmp_path: Path):
    """Hand-crafted hop3.nix only — accept (or reject if nix unavailable)."""
    (tmp_path / "hop3.nix").write_text("# placeholder")
    builder = NixBuilder(_make_context(tmp_path, {"hop3_config": {}}))
    # Should not raise — contradiction check passes
    try:
        builder.accept()
    except Abort:
        pytest.fail("Should not abort with only hop3.nix present")


def test_accept_with_only_nix_template(tmp_path: Path):
    """Template-only — accept (or reject if nix unavailable)."""
    builder = NixBuilder(
        _make_context(
            tmp_path,
            {"hop3_config": {"nix": {"template": "prebuilt-binary"}}},
        )
    )
    try:
        builder.accept()
    except Abort:
        pytest.fail("Should not abort with only [nix].template present")


def test_accept_with_neither(tmp_path: Path):
    """No hop3.nix, no template — return False, do not raise."""
    builder = NixBuilder(_make_context(tmp_path, {"hop3_config": {}}))
    assert builder.accept() is False


def test_accept_aborts_when_both_present(tmp_path: Path):
    """Both hop3.nix and [nix].template — must abort with actionable error."""
    (tmp_path / "hop3.nix").write_text("# placeholder")
    builder = NixBuilder(
        _make_context(
            tmp_path,
            {"hop3_config": {"nix": {"template": "prebuilt-binary"}}},
        )
    )

    with pytest.raises(Abort) as exc_info:
        builder.accept()

    msg = str(exc_info.value)
    assert "hop3.nix" in msg
    assert "[nix].template" in msg
    # Error must point to a remedy
    assert "Delete hop3.nix" in msg or "Remove the [nix].template" in msg
    # Error must mention nix:eject as the conversion path
    assert "nix eject" in msg


def test_build_aborts_when_both_present(tmp_path: Path):
    """build() also defends against the contradiction (force-selected case)."""
    (tmp_path / "hop3.nix").write_text("# placeholder")
    builder = NixBuilder(
        _make_context(
            tmp_path,
            {"hop3_config": {"nix": {"template": "prebuilt-binary"}}},
        )
    )

    with pytest.raises(Abort):
        builder.build()


def test_nix_build_registers_gc_root_via_out_link(tmp_path: Path, monkeypatch):
    """
    The build must root its closure with --out-link to <app>/.nix-result,
    not --no-out-link. Otherwise a later nix garbage-collect (or auto-GC under
    disk pressure) deletes a *running* app's binary — e.g. forgejo's wrapper
    execs the hardcoded ${forgejo}/bin/forgejo and the daemon dies with
    "No such file or directory". The root lives in the app dir (parent of src/,
    which the deployer git-cleans) so teardown removes it and frees the closure.
    """
    captured: dict[str, str] = {}

    def fake_run(self, cmd, cwd=None):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="/nix/store/xxx-app\n", stderr=""
        )

    monkeypatch.setattr(NixBuilder, "_run_nix_command", fake_run)
    builder = NixBuilder(_make_context(tmp_path, {"hop3_config": {}}))
    nix_file = tmp_path / "hop3.nix"
    nix_file.write_text("# placeholder")

    store_path = builder._nix_build(nix_file)

    assert store_path == "/nix/store/xxx-app"
    assert "--no-out-link" not in captured["cmd"]
    assert "--out-link" in captured["cmd"]
    # GC root sits in the app directory (parent of source_path), not src/.
    assert str(tmp_path.parent / ".nix-result") in captured["cmd"]


def test_nix_build_reregisters_previous_gc_root(tmp_path: Path, monkeypatch):
    """
    A rebuild must keep the immediately-prior closure rooted THROUGHOUT the
    build: a still-running old worker execs a hardcoded store path (forgejo's
    wrapper execs ${forgejo}/bin/forgejo), and a GC mid-rebuild would delete it.

    The builder must register a REAL indirect GC root for the old closure
    (`nix-store --realise <old> --add-root .nix-result-prev --indirect`) BEFORE
    nix-build. A plain `Path.rename` cannot carry a nix root (the gcroots/auto
    entry keeps pointing at the old name), and rotating after the build leaves an
    unrooted window — so this asserts the command, and that it precedes the build.
    """
    captured: list[str] = []

    def fake_run(self, cmd, cwd=None):
        captured.append(cmd)
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="/nix/store/new-app\n", stderr=""
        )

    monkeypatch.setattr(NixBuilder, "_run_nix_command", fake_run)
    src = tmp_path / "src"
    src.mkdir()
    builder = NixBuilder(_make_context(src, {"hop3_config": {}}))
    nix_file = src / "hop3.nix"
    nix_file.write_text("# placeholder")

    # The current root must point at a path that EXISTS on disk (a real prior
    # closure) — otherwise there is nothing to re-root.
    old_store = tmp_path / "old-app"
    old_store.mkdir()
    (tmp_path / ".nix-result").symlink_to(old_store)

    builder._nix_build(nix_file)

    reroot = [c for c in captured if "--add-root" in c and "--indirect" in c]
    assert reroot, "expected a nix-store --add-root --indirect for the old closure"
    assert "old-app" in reroot[0]
    assert ".nix-result-prev" in reroot[0]
    # Register-then-build: the old closure is rooted BEFORE nix-build starts, so
    # there is no unrooted window during the (multi-minute) build.
    build = [c for c in captured if "nix-build" in c]
    assert build, "expected a nix-build command"
    assert captured.index(reroot[0]) < captured.index(build[0])
