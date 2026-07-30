# Copyright (c) 2023-2026, Abilian SAS

"""Locating `nix-store`, and reading a closure query correctly.

This is a regression suite for a guard that was implemented, shipped, and never
once fired: it looked up `nix-store` on `PATH`, the deploy process has no Nix
profile sourced, so every deploy logged "check skipped" and continued. The
symptom it existed to prevent (a 180 s health-check timeout on a
garbage-collected closure) went on happening.

Each test below asserts a *rejection* — that the guard refuses — because a
guard whose tests only cover the happy path is how the first version passed
review.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from hop3.run.nix_closure import (
    NIX_STORE_CANDIDATES,
    ClosureCheckError,
    missing_closure_paths,
    resolve_nix_store,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestResolveNixStore:
    def test_prefers_an_absolute_candidate_over_path(self, tmp_path, monkeypatch):
        # The whole defect: a host can have a working Nix while `nix-store` is
        # absent from the deploy process's PATH.
        fake = tmp_path / "nix-store"
        fake.write_text("#!/bin/sh\n")
        fake.chmod(0o755)
        monkeypatch.setattr("hop3.run.nix_closure.NIX_STORE_CANDIDATES", (str(fake),))
        monkeypatch.setattr("shutil.which", lambda _: None)
        assert resolve_nix_store() == fake

    def test_returns_none_when_nothing_resolves(self, monkeypatch):
        monkeypatch.setattr(
            "hop3.run.nix_closure.NIX_STORE_CANDIDATES", ("/nonexistent/nix-store",)
        )
        monkeypatch.setattr("shutil.which", lambda _: None)
        assert resolve_nix_store() is None

    def test_ignores_a_candidate_that_is_not_executable(self, tmp_path, monkeypatch):
        fake = tmp_path / "nix-store"
        fake.write_text("")
        fake.chmod(0o644)
        monkeypatch.setattr("hop3.run.nix_closure.NIX_STORE_CANDIDATES", (str(fake),))
        monkeypatch.setattr("shutil.which", lambda _: None)
        assert resolve_nix_store() is None

    def test_every_candidate_is_absolute(self):
        # A bare name would reintroduce the PATH dependency this module exists to
        # remove; a `~` would reintroduce it in a subtler form, since the deploy
        # process's HOME is not the hop3 user's.
        for candidate in NIX_STORE_CANDIDATES:
            assert candidate.startswith("/"), candidate
            assert "~" not in candidate, candidate

    def test_covers_both_installer_modes(self):
        # The installer picks multi-user with systemd and single-user in
        # containers; a guard that knows only one silently skips on the other.
        joined = " ".join(NIX_STORE_CANDIDATES)
        assert "/nix/var/nix/profiles/default" in joined, "multi-user mode missing"
        assert ".nix-profile" in joined, "single-user mode missing"


def _stub_nix_store(
    tmp_path: Path, *, lines: tuple[str, ...] = (), rc: int = 0
) -> Path:
    script = tmp_path / "nix-store"
    body = "".join(f'echo "{line}"\n' for line in lines)
    script.write_text(f"#!/bin/sh\n{body}exit {rc}\n")
    script.chmod(0o755)
    return script


class TestMissingClosurePaths:
    def test_intact_closure_reports_nothing(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        dep = tmp_path / "dep"
        dep.mkdir()
        nix_store = _stub_nix_store(tmp_path, lines=(str(root), str(dep)))
        assert missing_closure_paths([str(root)], nix_store) == []

    def test_absent_root_is_reported_without_querying(self, tmp_path):
        nix_store = _stub_nix_store(tmp_path, rc=1)  # would raise if consulted
        missing = missing_closure_paths([str(tmp_path / "gone")], nix_store)
        assert missing == [str(tmp_path / "gone")]

    def test_reclaimed_dependency_is_reported(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        gone = tmp_path / "reclaimed"
        nix_store = _stub_nix_store(tmp_path, lines=(str(root), str(gone)))
        assert missing_closure_paths([str(root)], nix_store) == [str(gone)]

    def test_query_failure_raises_rather_than_reporting_clean(self, tmp_path):
        # The heart of it. A non-zero exit must not read as "nothing missing".
        root = tmp_path / "root"
        root.mkdir()
        nix_store = _stub_nix_store(tmp_path, rc=1)
        with pytest.raises(ClosureCheckError):
            missing_closure_paths([str(root)], nix_store)

    def test_unrunnable_binary_raises_rather_than_reporting_clean(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        with pytest.raises(ClosureCheckError):
            missing_closure_paths([str(root)], tmp_path / "does-not-exist")

    def test_timeout_raises_rather_than_reporting_clean(self, tmp_path, monkeypatch):
        root = tmp_path / "root"
        root.mkdir()
        nix_store = _stub_nix_store(tmp_path)

        def _timeout(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="nix-store", timeout=60)

        monkeypatch.setattr(subprocess, "run", _timeout)
        with pytest.raises(ClosureCheckError):
            missing_closure_paths([str(root)], nix_store)
