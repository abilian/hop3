# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
`hop3 app status` resource-[limits] surfacing (ADR 046 §3 / P2.2 B5).

The cap + enforcement mode come from the App row; the live OOM-kill count is a
best-effort hop3-rootd read (stubbed here — the kernel path is in hop3-rootd).
"""

from __future__ import annotations

from types import SimpleNamespace

import hop3.lib.rootd as rootd_mod
from hop3.commands.app import _limits_rows, _oom_kill_count


def _app(**kw):
    base = {"name": "myapp", "limits_enforced": "", "limits_detail": ""}
    return SimpleNamespace(**{**base, **kw})


class _StubClient:
    def __init__(self, result=None, raise_err=None):
        self._result = result or {}
        self._raise = raise_err

    def __enter__(self):
        if self._raise is not None:
            raise self._raise
        return self

    def __exit__(self, *_exc):
        return False

    def call(self, _op, _args=None):
        return self._result


def _stub_rootd(monkeypatch, *, result=None, raise_err=None):
    monkeypatch.setattr(
        rootd_mod,
        "LocalRootdClient",
        lambda: _StubClient(result=result, raise_err=raise_err),
    )


# --- _limits_rows ---------------------------------------------------------


def test_no_limits_rows_when_unset():
    assert _limits_rows(_app()) == []


def test_docker_limits_row_no_oom(monkeypatch):
    # docker apps don't get a live OOM read (not a native cgroup leaf).
    rows = _limits_rows(_app(limits_enforced="docker", limits_detail="memory=512M"))
    assert rows == [["Limits", "memory=512M [docker]"]]


def test_unenforced_shows_mode():
    rows = _limits_rows(
        _app(
            limits_enforced="unenforced", limits_detail="memory=512M (NOT enforced: x)"
        )
    )
    assert rows == [["Limits", "memory=512M (NOT enforced: x) [unenforced]"]]


def test_native_limits_row_includes_oom(monkeypatch):
    _stub_rootd(monkeypatch, result={"oom_kill": 4})
    rows = _limits_rows(_app(limits_enforced="native", limits_detail="memory=512M"))
    assert rows == [["Limits", "memory=512M [native]"], ["OOM kills", "4"]]


def test_native_no_oom_row_when_zero(monkeypatch):
    _stub_rootd(monkeypatch, result={"oom_kill": 0})
    rows = _limits_rows(_app(limits_enforced="native", limits_detail="memory=512M"))
    assert rows == [["Limits", "memory=512M [native]"]]


# --- _oom_kill_count ------------------------------------------------------


def test_oom_count_none_for_docker():
    assert _oom_kill_count(_app(limits_enforced="docker")) is None


def test_oom_count_reads_native(monkeypatch):
    _stub_rootd(monkeypatch, result={"oom_kill": 3})
    assert _oom_kill_count(_app(limits_enforced="native")) == 3


def test_oom_count_none_on_rootd_error(monkeypatch):
    _stub_rootd(monkeypatch, raise_err=rootd_mod.RootdError("down"))
    assert _oom_kill_count(_app(limits_enforced="native")) is None
