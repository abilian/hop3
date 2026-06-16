# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Native [limits] cgroup enforcement (ADR 046 §3 / P2.2).

The rootd client and /proc scan are stubbed — this is the server-side policy
(resolve → apply → strict/best-effort branching → record), not the kernel path
(that is unit-tested in hop3-rootd and only real-kernel-verified on a Linux run).
"""

from __future__ import annotations

from functools import partial
from types import SimpleNamespace
from typing import ClassVar

import pytest

from hop3.config import HopConfig
from hop3.deployers import native_limits as nl
from hop3.lib import Abort


class _FakeLoader:
    def __init__(self, values: dict) -> None:
        self.values = values

    def get_str(self, key, default=""):
        return self.values.get(key, default)

    def get_bool(self, key, default=False):
        return self.values.get(key, default)

    def get_int(self, key, default=0):
        return self.values.get(key, default)

    def get_float(self, key, default=0.0):
        return self.values.get(key, default)


@pytest.fixture
def set_config():
    def _set(**values):
        HopConfig.set_instance(HopConfig(config_loader=_FakeLoader(values)))

    yield _set
    HopConfig.reset_instance()


class _StubClient:
    """Records op calls; optionally raises a given error on connect/call."""

    calls: ClassVar[list[tuple[str, dict]]] = []

    def __init__(self, *, raise_on_enter=None, attach_failed=None):
        self.raise_on_enter = raise_on_enter
        self.attach_failed = attach_failed or []

    def __enter__(self):
        if self.raise_on_enter is not None:
            raise self.raise_on_enter
        return self

    def __exit__(self, *_exc):
        return False

    def call(self, op, args=None):
        type(self).calls.append((op, args or {}))
        if op == "cgroup.attach_pids":
            return {"attached": args["pids"], "failed": self.attach_failed}
        return {}


@pytest.fixture(autouse=True)
def _reset_calls():
    _StubClient.calls = []
    yield
    _StubClient.calls = []


def _patch(monkeypatch, *, pids, client_factory):
    monkeypatch.setattr(nl, "app_pids", lambda _name: pids)
    monkeypatch.setattr(nl, "LocalRootdClient", client_factory)


def _app(runtime="uwsgi"):
    return SimpleNamespace(
        name="myapp", runtime=runtime, limits_enforced="", limits_detail=""
    )


def _cfg(limits):
    return SimpleNamespace(hop3_config=SimpleNamespace(limits=dict(limits)))


# --- enforce: happy path --------------------------------------------------


def test_enforce_applies_and_records_native(monkeypatch, set_config):
    set_config()
    _patch(monkeypatch, pids=[101, 202], client_factory=_StubClient)
    app = _app()

    nl.enforce_native_limits(app, _cfg({"memory": "512M", "cpu": 1.5}))

    assert app.limits_enforced == "native"
    assert "memory=512M" in app.limits_detail
    ops = [c[0] for c in _StubClient.calls]
    assert ops == ["cgroup.ensure_slice", "cgroup.set_limits", "cgroup.attach_pids"]
    set_args = dict(_StubClient.calls[1][1])
    assert set_args["app_name"] == "myapp"
    assert set_args["memory_max"] == 512 * 1024**2
    assert _StubClient.calls[2][1]["pids"] == [101, 202]


def test_enforce_skips_docker_runtime(monkeypatch, set_config):
    set_config()
    _patch(monkeypatch, pids=[1], client_factory=_StubClient)
    app = _app(runtime="docker-compose")
    nl.enforce_native_limits(app, _cfg({"memory": "512M"}))
    assert _StubClient.calls == []
    assert app.limits_enforced == ""


def test_enforce_empty_resolution_removes_stale_leaf(monkeypatch, set_config):
    # A redeploy that drops [limits] from a previously-capped app must drop the
    # leaf AND clear the recorded state (else status lies / re-attach pokes a
    # dead leaf). Start from a prior "native" enforcement to prove it's cleared.
    set_config()  # no declared, no server defaults
    _patch(monkeypatch, pids=[1], client_factory=_StubClient)
    app = _app()
    app.limits_enforced = "native"
    app.limits_detail = "memory=512M"
    nl.enforce_native_limits(app, _cfg({}))
    assert [c[0] for c in _StubClient.calls] == ["cgroup.remove"]
    assert app.limits_enforced == ""
    assert app.limits_detail == ""


def test_enforce_aborts_on_ceiling_breach_post_start(monkeypatch, set_config):
    # The operator lowered the ceiling between build and post-start; re-resolution
    # now breaches it. Must be a structured abort, not an opaque LimitsError.
    set_config(LIMITS_CEILING_MEMORY="256M")
    _patch(monkeypatch, pids=[1], client_factory=_StubClient)
    with pytest.raises(Abort, match="breached the server ceiling"):
        nl.enforce_native_limits(_app(), _cfg({"memory": "512M"}))


def test_enforce_applies_server_default(monkeypatch, set_config):
    set_config(LIMITS_DEFAULT_MEMORY="256M")
    _patch(monkeypatch, pids=[7], client_factory=_StubClient)
    app = _app()
    nl.enforce_native_limits(app, _cfg({}))
    assert app.limits_enforced == "native"
    assert "memory=256M" in app.limits_detail


# --- enforce: strict failures abort ---------------------------------------


def test_enforce_strict_aborts_when_rootd_unavailable(monkeypatch, set_config):
    set_config()  # LIMITS_STRICT defaults True
    err = nl.RootdUnavailableError("socket missing")
    _patch(
        monkeypatch,
        pids=[1],
        client_factory=partial(_StubClient, raise_on_enter=err),
    )
    with pytest.raises(Abort, match="could not apply caps"):
        nl.enforce_native_limits(_app(), _cfg({"memory": "512M"}))


def test_enforce_strict_aborts_when_no_pids(monkeypatch, set_config):
    set_config()
    _patch(monkeypatch, pids=[], client_factory=_StubClient)
    with pytest.raises(Abort, match="no running processes"):
        nl.enforce_native_limits(_app(), _cfg({"memory": "512M"}))


def test_enforce_strict_aborts_on_partial_attach(monkeypatch, set_config):
    set_config()
    _patch(
        monkeypatch,
        pids=[1, 2],
        client_factory=partial(_StubClient, attach_failed=[2]),
    )
    with pytest.raises(Abort, match="could not be attached"):
        nl.enforce_native_limits(_app(), _cfg({"memory": "512M"}))


# --- enforce: best-effort records unenforced, never aborts -----------------


def test_enforce_best_effort_records_unenforced(monkeypatch, set_config):
    set_config(LIMITS_STRICT=False)
    err = nl.RootdUnavailableError("socket missing")
    _patch(
        monkeypatch,
        pids=[1],
        client_factory=partial(_StubClient, raise_on_enter=err),
    )
    app = _app()
    nl.enforce_native_limits(app, _cfg({"memory": "512M"}))  # no raise
    assert app.limits_enforced == "unenforced"
    assert "NOT enforced" in app.limits_detail


def test_enforce_best_effort_op_rejected_records_unenforced(monkeypatch, set_config):
    set_config(LIMITS_STRICT=False)
    err = nl.RootdError("kernel_error: cgroup write failed")
    _patch(
        monkeypatch,
        pids=[1],
        client_factory=partial(_StubClient, raise_on_enter=err),
    )
    app = _app()
    nl.enforce_native_limits(app, _cfg({"memory": "512M"}))  # no raise
    assert app.limits_enforced == "unenforced"


# --- reattach: best-effort, idempotent ------------------------------------


def test_reattach_attaches_live_pids(monkeypatch):
    _patch(monkeypatch, pids=[9], client_factory=_StubClient)
    nl.reattach_native_limits("myapp")
    assert _StubClient.calls == [
        ("cgroup.attach_pids", {"app_name": "myapp", "pids": [9]})
    ]


def test_reattach_noop_when_no_pids(monkeypatch):
    _patch(monkeypatch, pids=[], client_factory=_StubClient)
    nl.reattach_native_limits("myapp")
    assert _StubClient.calls == []


def _capture_log(monkeypatch):
    """Capture native_limits.log() messages (it is not stdlib logging)."""
    msgs: list[str] = []
    monkeypatch.setattr(nl, "log", lambda msg, **_kw: msgs.append(msg))
    return msgs


def test_reattach_swallows_rootd_error_but_logs(monkeypatch):
    msgs = _capture_log(monkeypatch)
    err = nl.RootdError("down")
    _patch(
        monkeypatch, pids=[9], client_factory=partial(_StubClient, raise_on_enter=err)
    )
    nl.reattach_native_limits("myapp")  # must not raise
    assert any("re-attach for 'myapp' failed" in m for m in msgs)


def test_reattach_logs_partial_failure(monkeypatch):
    # attach_pids succeeded at the transport level but reported failed PIDs — a
    # silently-uncapped process. Must surface, not pass quietly.
    msgs = _capture_log(monkeypatch)
    _patch(
        monkeypatch,
        pids=[9, 10],
        client_factory=partial(_StubClient, attach_failed=[10]),
    )
    nl.reattach_native_limits("myapp")  # must not raise
    assert any("could not be placed under the cap" in m for m in msgs)


# --- remove: best-effort teardown -----------------------------------------


def test_remove_calls_cgroup_remove(monkeypatch):
    _patch(monkeypatch, pids=[], client_factory=_StubClient)
    nl.remove_native_limits("myapp")
    assert _StubClient.calls == [("cgroup.remove", {"app_name": "myapp"})]


def test_remove_swallows_rootd_error(monkeypatch):
    err = nl.RootdError("down")
    _patch(
        monkeypatch, pids=[], client_factory=partial(_StubClient, raise_on_enter=err)
    )
    nl.remove_native_limits("myapp")  # must not raise
