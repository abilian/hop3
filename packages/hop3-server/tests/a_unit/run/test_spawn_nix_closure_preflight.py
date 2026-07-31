# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Deploy-time Nix closure-integrity pre-flight (M2.2 runtime hardening).

A nix wrapper execs hardcoded `/nix/store` paths; if a garbage-collect reclaimed
one (the forgejo class), the worker dies "No such file or directory" and only
surfaces as a 180s health-check timeout. `verify_nix_closure_intact` catches it
before uWSGI starts and aborts with a named error.

These test the *logic*: store-path extraction, the abort decision, and — since
2026-07-30 — that the guard refuses rather than continues when it cannot run.
`nix-store` is now resolved by absolute path (`hop3.run.nix_closure`), which was
the reason the guard silently skipped on every real deploy. End-to-end
confirmation, deleting a path from a live closure and observing the abort, still
needs a real nix host; see `local-notes/plans/30-nix-runtime-1.0.md`.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from hop3.core.artifacts import BuildArtifact, RuntimeConfig
from hop3.lib import Abort
from hop3.run.nix_closure import ClosureCheckError
from hop3.run.spawn import AppLauncher, _extract_nix_store_paths

_H1, _H2, _H3 = "a" * 32, "b" * 32, "c" * 32


def _nix_launcher(worker_cmd: str, *, kind: str = "nix") -> AppLauncher:
    launcher = AppLauncher.__new__(AppLauncher)
    launcher.app_name = "forge"
    launcher.artifact = BuildArtifact(
        kind=kind, runtime=RuntimeConfig(workers={"web": worker_cmd})
    )
    return launcher


def _patch_exists(monkeypatch, *, present: set[str], absent: set[str]) -> None:
    """
    Force existence for our fake store paths; defer to the real check for
    everything else (so pytest's own file access is unaffected).
    """
    real = os.path.exists

    def fake(p):
        if p in present:
            return True
        if p in absent:
            return False
        return real(p)

    monkeypatch.setattr("os.path.exists", fake)


def test_extract_nix_store_paths_returns_root() -> None:
    cmds = [f"/nix/store/{_H1}-forgejo-11.0.1/bin/forgejo web", "echo hi"]
    assert _extract_nix_store_paths(cmds) == [f"/nix/store/{_H1}-forgejo-11.0.1"]


def test_aborts_when_closure_path_gc_reclaimed(monkeypatch) -> None:
    root = f"/nix/store/{_H1}-forgejo"
    dep_ok = f"/nix/store/{_H2}-glibc"
    dep_gone = f"/nix/store/{_H3}-forgejo-inner"  # the reclaimed sibling
    launcher = _nix_launcher(f"{root}/bin/forgejo web")

    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: SimpleNamespace(
            returncode=0, stdout=f"{root}\n{dep_ok}\n{dep_gone}\n", stderr=""
        ),
    )
    _patch_exists(monkeypatch, present={root, dep_ok}, absent={dep_gone})

    with pytest.raises(Abort, match="garbage-collected"):
        launcher.verify_nix_closure_intact()


def test_passes_when_closure_intact(monkeypatch) -> None:
    root = f"/nix/store/{_H1}-forgejo"
    dep = f"/nix/store/{_H2}-glibc"
    launcher = _nix_launcher(f"{root}/bin/forgejo web")

    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: SimpleNamespace(
            returncode=0, stdout=f"{root}\n{dep}\n", stderr=""
        ),
    )
    _patch_exists(monkeypatch, present={root, dep}, absent=set())

    launcher.verify_nix_closure_intact()  # no raise


def test_skips_non_nix_artifact(monkeypatch) -> None:
    called: list[int] = []

    def fake_run(*a, **k):
        called.append(1)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    launcher = _nix_launcher(f"/nix/store/{_H1}-x/bin/x", kind="python")

    launcher.verify_nix_closure_intact()  # early return

    assert not called  # never shells out for a non-nix artifact


def test_aborts_when_nix_store_unavailable(monkeypatch) -> None:
    """A guard that cannot run must say so, not wave the deploy through.

    This test asserted the opposite until 2026-07-30. `nix-store` is not on the
    deploy process's PATH on a normally-installed host, so the guard logged a
    skip on every deploy and never fired — including on the forgejo timeout it
    was written to diagnose. Silently continuing let that go unnoticed.
    """
    root = f"/nix/store/{_H1}-forgejo"
    launcher = _nix_launcher(f"{root}/bin/forgejo web")

    monkeypatch.setattr("hop3.run.spawn.resolve_nix_store", lambda: None)
    _patch_exists(monkeypatch, present={root}, absent=set())

    with pytest.raises(Abort, match="could not be found"):
        launcher.verify_nix_closure_intact()


def test_aborts_when_the_closure_query_is_inconclusive(monkeypatch, tmp_path) -> None:
    """An erroring query must not read as "nothing missing"."""
    root = f"/nix/store/{_H1}-forgejo"
    launcher = _nix_launcher(f"{root}/bin/forgejo web")

    def _raise(*a, **k):
        msg = "nix-store exited 1"
        raise ClosureCheckError(msg)

    monkeypatch.setattr("hop3.run.spawn.resolve_nix_store", lambda: tmp_path / "ns")
    monkeypatch.setattr("hop3.run.spawn.missing_closure_paths", _raise)
    _patch_exists(monkeypatch, present={root}, absent=set())

    with pytest.raises(Abort, match="could not be checked"):
        launcher.verify_nix_closure_intact()
