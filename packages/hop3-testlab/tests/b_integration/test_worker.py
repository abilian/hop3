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
from hop3_testlab.worker import RunSpec, run_once


def _session():
    return get_session_factory(str(TestlabConfig.get_instance().DB_PATH))()


def test_run_once_runs_and_releases_the_lease():
    calls: list[tuple] = []
    ran = run_once(
        "docker",
        trigger="t",
        mode="ci",
        executor=lambda tid, m, apps, **_kw: calls.append((tid, m, apps)),
    )

    assert ran is True
    assert calls == [("docker", "ci", None)]
    # Lease released -> a second run can proceed.
    ran2 = run_once("docker", trigger="t", executor=lambda tid, m, apps, **_kw: None)
    assert ran2 is True


def test_run_once_passes_apps_through(monkeypatch):
    seen = {}
    run_once(
        "docker",
        trigger="t",
        spec=RunSpec(apps=["apps/real-apps-docker/invoice-ninja"]),
        executor=lambda tid, m, apps, **_kw: seen.update(apps=apps),
    )
    assert seen["apps"] == ["apps/real-apps-docker/invoice-ninja"]


def test_run_once_is_busy_when_lease_held():
    with _session() as s:  # someone else holds the target
        leasing.try_acquire(s, "docker", "other")

    def _must_not_run(_tid, _m, _apps, **_kw):
        pytest.fail("executor ran while the target was busy")

    assert run_once("docker", trigger="t", executor=_must_not_run) is False


def test_run_once_tags_trigger_in_env_during_run(monkeypatch):
    monkeypatch.delenv("HOP3_TEST_TRIGGER", raising=False)
    seen: dict[str, str | None] = {}

    def _capture(_tid, _m, _apps, **_kw):
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
    monkeypatch.setattr(leasing, "proc_starttime", lambda _pid: 222)  # differs now
    worker.terminate_engine(4321, starttime=111)
    assert calls == []  # never signalled the recycled PID


def test_terminate_engine_signals_when_identity_matches(monkeypatch):
    sent: list[int] = []
    monkeypatch.setattr(worker, "STOP_GRACE_SECONDS", 0.01)
    monkeypatch.setattr(worker.os, "killpg", lambda _pid, sig: sent.append(sig))
    monkeypatch.setattr(leasing, "proc_starttime", lambda _pid: 111)
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
    assert leasing.proc_starttime(os.getpid()) is not None
    assert leasing.proc_starttime(2**31 - 1) is None  # almost certainly no such pid


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
    monkeypatch.setattr(
        worker, "_run_engine", lambda tid, cmd, env, cwd=None: calls.append(cmd)
    )

    worker._default_executor("docker", "nightly", None)

    cmd = calls[0]
    assert cmd[cmd.index("--with") + 1] == "all"
    assert "--docker" in cmd
    assert cmd[cmd.index("--mode") + 1] == "nightly"


def test_default_executor_per_app_build(monkeypatch):
    # Per-app build: the app path scopes the run (positional). --mode is still
    # passed, but only as the recorded scope label — the engine ignores it for
    # *selection* when explicit apps are given, so the dashboard shows the real
    # selection instead of the engine's --mode default.
    calls = []
    monkeypatch.setattr(
        worker, "_run_engine", lambda tid, cmd, env, cwd=None: calls.append(cmd)
    )

    worker._default_executor("docker", "broad", ["apps/real-apps-docker/invoice-ninja"])

    cmd = calls[0]
    assert "apps/real-apps-docker/invoice-ninja" in cmd
    assert cmd[cmd.index("--mode") + 1] == "broad"  # record-only label
    assert cmd[cmd.index("--with") + 1] == "all"


def test_run_once_releases_lease_even_if_executor_raises():
    def _boom(_tid, _m, _apps, **_kw):
        msg = "deploy blew up"
        raise RuntimeError(msg)

    with pytest.raises(RuntimeError, match="deploy blew up"):
        run_once("docker", trigger="t", executor=_boom)

    # The lease must have been released despite the failure.
    ran = run_once("docker", trigger="t", executor=lambda tid, m, apps, **_kw: None)
    assert ran is True


def test_run_once_composes_source_ref_and_platform_ref(monkeypatch, tmp_path):
    """source@source_ref is fetched, the selector is resolved against that
    workspace, and the platform ref + workspace cwd reach the executor (§A)."""
    workspace = tmp_path / "ws"

    class _FakeSource:
        name = "main-repo"

        def __init__(self):
            self.fetched: list[str] = []

        def fetch(self, ref):
            self.fetched.append(ref)
            return workspace

    fake = _FakeSource()
    monkeypatch.setattr(worker, "resolve_selector", lambda root, pat: [f"{root}:{pat}"])
    seen: dict = {}

    def _exec(tid, m, apps, *, platform_ref=None, cwd=None, **_kw):
        seen.update(apps=apps, platform_ref=platform_ref, cwd=cwd)

    ran = run_once(
        "docker",
        trigger="t",
        mode="coverage",
        spec=RunSpec(
            source=fake, source_ref="devel", platform_ref="main", selector="apps/*"
        ),
        executor=_exec,
    )

    assert ran is True
    assert fake.fetched == ["devel"]  # apps ref fetched
    assert seen["apps"] == [f"{workspace}:apps/*"]  # selector resolved vs the workspace
    assert seen["platform_ref"] == "main"  # platform ref passed through
    assert seen["cwd"] == workspace  # engine runs from the fetched workspace


def test_run_once_resolves_profile_selection(monkeypatch, tmp_path):
    """A profile run resolves its `selection` rules (via the engine Selector)
    against the fetched workspace catalog, not a hand-picked app list."""

    class _Src:
        name = "main-repo"

        def fetch(self, _ref):
            return tmp_path

    monkeypatch.setattr(worker, "build_catalog", lambda _root: "CATALOG")
    monkeypatch.setattr(
        worker, "resolve_selection", lambda _catalog, _selection: ["apps/a", "apps/b"]
    )
    seen: dict = {}

    def _exec(_tid, _m, apps, **_kw):
        seen["apps"] = apps

    run_once(
        "docker",
        trigger="t",
        spec=RunSpec(source=_Src(), source_ref="devel", selection={"mode": "smoke"}),
        executor=_exec,
    )
    assert seen["apps"] == ["apps/a", "apps/b"]


def test_default_executor_deploys_platform_ref_from_git(monkeypatch, tmp_path):
    """platform_ref must be installed FROM GIT (`--from git --branch X`),
    not recorded while local code is deployed (review #6); cwd reaches the spawn."""
    calls: list[tuple] = []
    monkeypatch.setattr(
        worker,
        "_run_engine",
        lambda tid, cmd, env, cwd=None: calls.append((cmd, cwd)),
    )

    worker._default_executor(
        "docker", "nightly", ["apps/foo"], platform_ref="main", cwd=tmp_path
    )

    cmd, cwd = calls[0]
    assert cmd[cmd.index("--from") + 1] == "git"  # else --branch is ignored
    assert (
        cmd[cmd.index("--branch") + 1] == "main"
    )  # platform ref -> hop3-deploy-server
    assert "apps/foo" in cmd  # resolved app, positional
    assert cwd == tmp_path  # engine scans/deploys from the workspace


def test_default_executor_no_platform_ref_stays_local(monkeypatch):
    """No platform_ref -> no `--from git` (engine default: local code)."""
    calls: list[tuple] = []
    monkeypatch.setattr(
        worker, "_run_engine", lambda tid, cmd, env, cwd=None: calls.append((cmd, cwd))
    )
    worker._default_executor("docker", "smoke", apps=None)
    cmd = calls[0][0]
    assert "--from" not in cmd
    assert "--deploy-from" not in cmd  # neither spelling


def test_run_engine_raises_on_nonzero_exit(monkeypatch, tmp_path):
    """A non-zero engine exit fails loud with the log path (was swallowed)."""

    class _Proc:
        pid = 4242

        def wait(self):
            return 1  # the engine failed

    monkeypatch.setattr(worker.subprocess, "Popen", lambda *a, **k: _Proc())
    monkeypatch.setattr(worker, "_record_engine_pid", lambda *a, **k: None)
    monkeypatch.setattr(worker, "_engine_log_path", lambda env: tmp_path / "engine.log")
    with pytest.raises(RuntimeError, match="Engine exited 1"):
        worker._run_engine("docker", ["hop3-test", "run"], None)


def test_failure_summary_surfaces_failed_tests_not_the_ok_tail(tmp_path):
    """The engine prints its "Failed tests" block, then keeps going with a
    passing-demos recap + teardown. A plain tail shows only the trailing OK
    lines and hides the real cause — the detail must surface the failures."""
    log = tmp_path / "engine.log"
    log.write_text(
        "\n".join([
            "[discourse] Deploying discourse-1782127545...",
            "============================================================",
            "2 of 29 tests failed",
            "Total time: 2158.95s",
            "============================================================",
            "",
            "Failed tests:",
            "  ✗ discourse",
            "      ✗ build-failure — discourse-1782127545",
            "  ✗ focalboard",
            "      ✗ app-crash — focalboard-1782128505",
            "",
            "Full per-test logs: test-logs/system-20260622/app-logs/",
            "",
            "Per-app results:",
            "  - discourse (apps/real-apps-docker/discourse): FAIL",
            # the misleading all-OK tail the old tail-only detail would show:
            *(f"  - demos/demo0{i}: OK" for i in range(1, 7)),
            "Stopping target...",
            "Remote target cleanup complete (server keeps running).",
        ]),
        encoding="utf-8",
    )
    summary = worker._failure_summary(log)
    assert "2 of 29 tests failed" in summary
    assert "discourse" in summary
    assert "build-failure" in summary
    assert "focalboard" in summary
    assert "app-crash" in summary
    # stops at the per-test-logs boundary — no trailing OK / teardown leakage
    assert "demos/demo06: OK" not in summary
    assert "Remote target cleanup complete" not in summary


def test_failure_summary_falls_back_to_tail_without_a_failed_block(tmp_path):
    """A setup/deploy abort prints no "N of M tests failed" banner, so the
    detail falls back to the tail rather than going blank."""
    log = tmp_path / "engine.log"
    log.write_text(
        "fetching source...\nblank-slate refused: dirty server\nABORTED\n",
        encoding="utf-8",
    )
    assert "ABORTED" in worker._failure_summary(log)


def test_sweep_skips_a_run_live_on_another_target():
    """A healthy run on target B is not aborted by a run starting on target A (#2)."""
    from hop3_testing.results.models import TestRun

    factory = get_session_factory(TestlabConfig.get_instance().STORE_TARGET)
    with factory() as s:  # B is running: live lease + an unfinished run
        leasing.try_acquire(s, "B", "build-B")
        s.add(
            TestRun(
                run_uid="run-B", trigger="build-B", mode="smoke", target_type="docker"
            )
        )
        s.commit()

    seen = {}

    def _exec(_tid, _m, _apps, **_kw):
        with factory() as s:
            run_b = s.query(TestRun).filter_by(run_uid="run-B").one()
            seen["b_finished_at"] = run_b.finished_at

    run_once("A", trigger="build-A", executor=_exec)
    assert seen["b_finished_at"] is None  # B's run survived A's orphan-sweep


def test_run_once_fails_loud_on_source_without_ref():
    """A source with a blank ref must raise, not silently run the local suite."""

    class _Src:
        name = "main-repo"

        def fetch(self, _ref):
            pytest.fail("must not fetch with a blank ref")

    with pytest.raises(ValueError, match="without a source_ref"):
        run_once("docker", trigger="t", spec=RunSpec(source=_Src(), source_ref=""))


def test_run_once_legacy_run_defaults_cwd_to_repo_root():
    """A no-source run must run the engine from the repo root (where apps/ lives),
    not the Lab's own cwd — else the engine's default scan finds no apps."""
    from hop3_testing.targets.helpers import find_project_root

    seen: dict = {}

    def _exec(_tid, _m, _apps, *, cwd=None, **_kw):
        seen["cwd"] = cwd

    run_once("docker", trigger="t", mode="ci", executor=_exec)
    assert seen["cwd"] == find_project_root()


def test_run_once_records_provenance(monkeypatch, tmp_path):
    """The run's composition identity (source / apps_ref / platform_ref / runner)
    is built and handed to the executor as `provenance` (-> HOP3_TEST_META)."""

    class _Src:
        name = "main-repo"

        def fetch(self, _ref):
            return tmp_path

    monkeypatch.setattr(worker, "resolve_selector", lambda root, pat: ["apps/x"])
    seen: dict = {}

    def _exec(tid, m, apps, *, provenance=None, **_kw):
        seen["provenance"] = provenance

    run_once(
        "docker",
        trigger="t",
        mode="coverage",
        spec=RunSpec(
            source=_Src(), source_ref="devel", platform_ref="main", selector="apps/*"
        ),
        executor=_exec,
    )

    p = seen["provenance"]
    assert p["source_name"] == "main-repo"
    assert p["apps_ref"] == "devel"  # the apps came from this ref
    assert p["platform_ref"] == "main"  # against this platform ref
    assert "runner_version" in p  # and this engine version
