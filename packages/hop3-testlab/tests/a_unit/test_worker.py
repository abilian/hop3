# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""The run worker: lease lifecycle around the (stubbed) executor."""

from __future__ import annotations

import os
import signal
from pathlib import Path
from types import SimpleNamespace

import pytest
from hop3_testlab import leasing, worker
from hop3_testlab.config import TestlabConfig
from hop3_testlab.db import get_session_factory
from hop3_testlab.worker import run_once


def _session():
    return get_session_factory(str(TestlabConfig.get_instance().DB_PATH))()


def test_run_once_runs_and_releases_the_lease():
    calls: list[tuple] = []
    ran = run_once(
        "docker",
        trigger="t",
        mode="ci",
        executor=lambda tid, m, apps: calls.append((tid, m, apps)),
    )

    assert ran is True
    assert calls == [("docker", "ci", None)]
    # Lease released -> a second run can proceed.
    ran2 = run_once("docker", trigger="t", executor=lambda tid, m, apps: None)
    assert ran2 is True


def test_run_once_passes_apps_through(monkeypatch):
    seen = {}
    run_once(
        "docker",
        trigger="t",
        apps=["apps/real-apps-docker/invoice-ninja"],
        executor=lambda tid, m, apps: seen.update(apps=apps),
    )
    assert seen["apps"] == ["apps/real-apps-docker/invoice-ninja"]


def test_run_once_is_busy_when_lease_held():
    with _session() as s:  # someone else holds the target
        leasing.try_acquire(s, "docker", "other")

    def _must_not_run(_tid, _m, _apps):
        pytest.fail("executor ran while the target was busy")

    assert run_once("docker", trigger="t", executor=_must_not_run) is False


def test_run_once_tags_trigger_in_env_during_run(monkeypatch):
    monkeypatch.delenv("HOP3_TEST_TRIGGER", raising=False)
    seen: dict[str, str | None] = {}

    def _capture(_tid, _m, _apps):
        seen["trigger"] = os.environ.get("HOP3_TEST_TRIGGER")

    run_once("docker", trigger="scheduled-nightly", executor=_capture)

    assert seen["trigger"] == "scheduled-nightly"  # set for the spawned engine
    assert os.environ.get("HOP3_TEST_TRIGGER") is None  # and restored afterwards


def test_resolve_run_target_hetzner_harvests_server_info(monkeypatch):
    cfg = SimpleNamespace(
        hetzner_token="t", hetzner_server_id=1, hetzner_image="x", ssh_key_path="/k"
    )
    info = SimpleNamespace(
        ipv4="1.2.3.4", image="ubuntu-24.04", server_type="cx43", datacenter="hel1-dc2"
    )
    monkeypatch.setattr(worker, "load_cloud_config", lambda: cfg)
    monkeypatch.setattr(worker, "_hetzner_server_info", lambda _cfg: info)

    host, key, meta = worker._resolve_run_target("hetzner")
    assert host == "1.2.3.4"
    assert key == "/k"
    assert meta["os_name"] == "ubuntu"
    assert meta["os_version"] == "24.04"
    assert meta["server_type"] == "cx43"
    assert meta["datacenter"] == "hel1-dc2"


def test_terminate_engine_skips_recycled_pid(monkeypatch):
    """If the recorded start-time no longer matches, the PID was recycled — the
    group must NOT be signalled (the whole point of the identity check)."""
    calls: list[tuple] = []
    monkeypatch.setattr(worker.os, "killpg", lambda *a: calls.append(a))
    monkeypatch.setattr(worker, "_proc_starttime", lambda _pid: 222)  # differs now
    worker.terminate_engine(4321, starttime=111)
    assert calls == []  # never signalled the recycled PID


def test_terminate_engine_signals_when_identity_matches(monkeypatch):
    sent: list[int] = []
    monkeypatch.setattr(worker, "STOP_GRACE_SECONDS", 0.01)
    monkeypatch.setattr(worker.os, "killpg", lambda _pid, sig: sent.append(sig))
    monkeypatch.setattr(worker, "_proc_starttime", lambda _pid: 111)
    worker.terminate_engine(4321, starttime=111)
    assert signal.SIGTERM in sent  # our engine -> SIGTERM its group


def test_terminate_engine_without_starttime_probes_then_skips_when_gone(monkeypatch):
    """No recorded identity -> fall back to a liveness probe; a gone group is
    detected by the probe and nothing further is signalled."""
    calls: list[tuple] = []

    def _killpg(pid, sig):
        calls.append((pid, sig))
        raise ProcessLookupError  # group is gone

    monkeypatch.setattr(worker.os, "killpg", _killpg)
    worker.terminate_engine(999999, starttime=None)
    assert calls == [(999999, 0)]  # only the probe (signal 0), no SIGTERM


def test_proc_starttime_identifies_a_live_process():
    if not Path("/proc/self/stat").exists():
        pytest.skip("no procfs (non-Linux)")
    assert worker._proc_starttime(os.getpid()) is not None
    assert worker._proc_starttime(2**31 - 1) is None  # almost certainly no such pid


def test_resolve_run_target_plain_host_is_verbatim(monkeypatch):
    cfg = SimpleNamespace(
        hetzner_token="", hetzner_server_id=0, hetzner_image="x", ssh_key_path="/k"
    )
    monkeypatch.setattr(worker, "load_cloud_config", lambda: cfg)

    host, key, meta = worker._resolve_run_target("203.0.113.9")
    assert host == "203.0.113.9"  # not "hetzner" -> used as-is, no API call
    assert key == "/k"
    assert meta == {"target": "203.0.113.9"}


def test_default_executor_installs_addons_full_suite(monkeypatch):
    # Full build: --with all (addons) + --mode. The docker branch needs no network.
    # _run_engine is the spawn seam (Popen + PID recording); capture its cmd.
    calls = []
    monkeypatch.setattr(worker, "_run_engine", lambda tid, cmd, env: calls.append(cmd))

    worker._default_executor("docker", "nightly", None)

    cmd = calls[0]
    assert cmd[cmd.index("--with") + 1] == "all"
    assert "--docker" in cmd
    assert cmd[cmd.index("--mode") + 1] == "nightly"


def test_default_executor_per_app_build(monkeypatch):
    # Per-app build: the app path is passed positionally, not via --mode.
    calls = []
    monkeypatch.setattr(worker, "_run_engine", lambda tid, cmd, env: calls.append(cmd))

    worker._default_executor(
        "docker", "nightly", ["apps/real-apps-docker/invoice-ninja"]
    )

    cmd = calls[0]
    assert "apps/real-apps-docker/invoice-ninja" in cmd
    assert "--mode" not in cmd  # scoped to the app, not the whole suite
    assert cmd[cmd.index("--with") + 1] == "all"


def test_run_once_releases_lease_even_if_executor_raises():
    def _boom(_tid, _m, _apps):
        msg = "deploy blew up"
        raise RuntimeError(msg)

    with pytest.raises(RuntimeError, match="deploy blew up"):
        run_once("docker", trigger="t", executor=_boom)

    # The lease must have been released despite the failure.
    ran = run_once("docker", trigger="t", executor=lambda tid, m, apps: None)
    assert ran is True
