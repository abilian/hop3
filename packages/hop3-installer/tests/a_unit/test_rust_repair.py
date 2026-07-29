# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
A flaky rustup component download shouldn't hard-fail a deploy.

`--profile minimal` installs cargo, but a flaky download (or a stale ~/.rustup)
can leave the cargo proxy present while the stable toolchain has no cargo
component. `_verify_or_repair_cargo` force-reinstalls the toolchain once before
giving up — a self-heal that still fails loud when the toolchain is truly broken.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from types import SimpleNamespace

import hop3_installer.server_installer.deps_common as dc


def _result(returncode, stdout="cargo 1.0.0", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class _Recorder:
    """A fake run_as_hop3 that returns queued results and records commands."""

    def __init__(self, results):
        self._results = list(results)
        self.calls: list[list[str]] = []

    def __call__(self, argv, **_kwargs):
        self.calls.append(argv)
        return self._results.pop(0)


@contextlib.contextmanager
def _noop_spinner(*_args, **_kwargs):
    yield


CARGO = Path("/home/hop3/.cargo/bin/cargo")
RUSTUP = Path("/home/hop3/.cargo/bin/rustup")


def test_cargo_ok_needs_no_repair(monkeypatch):
    rec = _Recorder([_result(0)])
    monkeypatch.setattr(dc, "run_as_hop3", rec)
    assert dc._verify_or_repair_cargo(CARGO, RUSTUP).returncode == 0
    assert len(rec.calls) == 1  # verified once, never reinstalled


def test_broken_toolchain_is_repaired(monkeypatch):
    # verify fails -> forced reinstall -> re-verify succeeds.
    rec = _Recorder([_result(1, stderr="not applicable"), _result(0), _result(0)])
    monkeypatch.setattr(dc, "run_as_hop3", rec)
    monkeypatch.setattr(dc, "Spinner", _noop_spinner)
    assert dc._verify_or_repair_cargo(CARGO, RUSTUP).returncode == 0
    # run_as_hop3 takes argv (quoted at the seam); assert on the arguments,
    # not on a rendered command string.
    assert any(
        c[1:4] == ["toolchain", "install", "stable"] and "--force" in c
        for c in rec.calls
    ), rec.calls


def test_still_broken_after_repair_fails_loud(monkeypatch):
    # repair doesn't help -> the non-zero result propagates so the caller aborts.
    rec = _Recorder([_result(1), _result(0), _result(1, stderr="not applicable")])
    monkeypatch.setattr(dc, "run_as_hop3", rec)
    monkeypatch.setattr(dc, "Spinner", _noop_spinner)
    assert dc._verify_or_repair_cargo(CARGO, RUSTUP).returncode == 1
