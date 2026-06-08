# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""The run worker: take the lease, run the suite, release.

v1 reuses the existing engine by spawning ``hop3-test system`` as a subprocess
(the per-run-subprocess model in the spec §10); its results land in the shared
store, which the dashboard reads. The HetznerPool provisioning, the
Orchestrator(pool, shard) generalization, incremental/streamed persistence, and
provenance convergence (recording `trigger` on the run) are the remaining M4
work — see local-notes/specs/testlab-specs.md.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from hop3_testlab import leasing
from hop3_testlab.cloud_config import load_cloud_config
from hop3_testlab.config import TestlabConfig
from hop3_testlab.db import get_session_factory
from hop3_testlab.repositories import RunsRepository

if TYPE_CHECKING:
    from collections.abc import Callable

    from hop3_testlab.cloud_config import CloudConfig

STOP_GRACE_SECONDS = 5.0


def _hetzner_server_info(cfg: CloudConfig):
    """Fetch the configured Hetzner server's info (lazy: hcloud is heavy)."""
    from hop3_testing.system_tests.config import HetznerConfig  # noqa: PLC0415
    from hop3_testing.system_tests.hetzner import HetznerManager  # noqa: PLC0415

    hz = HetznerConfig(
        api_token=cfg.hetzner_token,
        server_id=cfg.hetzner_server_id,
        image=cfg.hetzner_image,
    )
    return HetznerManager(hz).get_server_info()


def _resolve_run_target(target_id: str) -> tuple[str, str | None, dict]:
    """Map a target id to (ssh_host, ssh_key_path, session_metadata).

    ``hetzner`` resolves to the configured server's IP and harvests its
    OS/type/datacenter as session metadata; any other non-docker id is the SSH
    host verbatim.
    """
    cfg = load_cloud_config()
    if target_id == "hetzner":
        info = _hetzner_server_info(cfg)
        meta = {
            "target": "hetzner",
            "server_type": info.server_type,
            "datacenter": info.datacenter,
            "image": info.image,
            "ipv4": info.ipv4,
        }
        if info.image and "-" in info.image:  # e.g. "ubuntu-24.04"
            name, _, version = info.image.partition("-")
            meta["os_name"], meta["os_version"] = name, version
        return info.ipv4, cfg.ssh_key_path, meta
    return target_id, cfg.ssh_key_path, {"target": target_id}


def _suite_args(mode: str, apps: list[str] | None) -> list[str]:
    """Engine args: specific app paths (positional) for a per-app build, else
    the whole mode-selected suite."""
    return list(apps) if apps else ["--mode", mode]


def _proc_starttime(pid: int) -> int | None:
    """The process start-time (jiffies since boot, ``/proc/<pid>/stat`` field 22).

    A reuse-proof identity for the engine PID: the kernel never reissues the same
    (pid, starttime) pair. Returns None when unreadable (process gone, or no
    procfs — e.g. a macOS dev machine), in which case identity can't be checked.
    """
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except (OSError, ValueError):
        return None
    # comm (field 2) is parenthesised and may contain spaces/parens; index from
    # the last ')' so the remaining whitespace-split fields line up.
    rparen = stat.rfind(")")
    if rparen == -1:
        return None
    fields = stat[rparen + 2 :].split()
    try:
        return int(fields[19])  # field 22 overall; 20th after comm -> index 19
    except (IndexError, ValueError):
        return None


def terminate_engine(pid: int, starttime: int | None = None) -> None:
    """Stop a running engine: SIGTERM its process group, SIGKILL after a grace.

    The engine is its own session leader (start_new_session), so ``pid == pgid``
    and signalling the group reaches the docker/ssh children it spawned. Before
    each signal the PID is checked against ``starttime`` (its recorded
    ``/proc`` start-time) so a recycled PID belonging to an unrelated process
    group is never signalled. When ``starttime`` is None (identity wasn't
    captured), it falls back to a liveness probe. The hard kill runs in a daemon
    thread so the web request returns immediately.
    """

    def _still_our_engine() -> bool:
        if starttime is not None:
            return _proc_starttime(pid) == starttime
        # No recorded identity: best-effort liveness probe (the old behaviour).
        try:
            os.killpg(pid, 0)
        except OSError:
            return False
        return True

    if not _still_our_engine():
        return
    with contextlib.suppress(OSError):
        os.killpg(pid, signal.SIGTERM)

    def _hard_kill() -> None:
        time.sleep(STOP_GRACE_SECONDS)
        if _still_our_engine():
            with contextlib.suppress(OSError):
                os.killpg(pid, signal.SIGKILL)

    threading.Thread(target=_hard_kill, daemon=True, name="stop-hard-kill").start()


def _record_engine_pid(target_id: str, pid: int) -> None:
    """Record the engine PID (+ start-time) on the lease so the dashboard can
    stop it without risking a recycled PID."""
    config = TestlabConfig.get_instance()
    factory = get_session_factory(str(config.DB_PATH))
    session = factory()
    try:
        leasing.set_pid(session, target_id, pid, _proc_starttime(pid))
    finally:
        session.close()


def _run_engine(target_id: str, cmd: list[str], env: dict | None) -> None:
    """Spawn the engine in its OWN session (killable as a process group) and wait.

    ``start_new_session=True`` makes the engine a session/group leader, so the
    dashboard's stop control can ``os.killpg`` the whole run (engine + the docker/
    ssh children it spawns) without touching this worker or the web app. We record
    the PID on the lease right after spawn, then block until it exits.
    """
    proc = subprocess.Popen(cmd, start_new_session=True, env=env)
    # Recording the PID is best-effort — never let it abort the run.
    with contextlib.suppress(Exception):
        _record_engine_pid(target_id, proc.pid)
    proc.wait()


def _default_executor(target_id: str, mode: str, apps: list[str] | None) -> None:
    """Run the suite via the existing engine (results -> shared store).

    ``--with all`` installs every addon feature (mysql/postgresql/redis/nix/…) so
    addon-dependent apps can provision; without it they fail at deploy time
    ("addon can't provision … re-run with --with <feature>"). ``apps`` scopes the
    run to specific app paths (a per-app build); otherwise the full mode suite.
    """
    if target_id in {"docker", ""}:
        cmd = [
            "hop3-test",
            "system",
            "--docker",
            "--with",
            "all",
            *_suite_args(mode, apps),
            "--report",
            "html",
        ]
        _run_engine(target_id, cmd, None)
        return

    host, ssh_key, meta = _resolve_run_target(target_id)
    env = dict(os.environ)
    if ssh_key:
        env["HOP3_TEST_SSH_KEY"] = ssh_key
    if meta:
        # Picked up by ResultStore.start_run -> run_metadata (session details).
        env["HOP3_TEST_META"] = json.dumps(meta)
    cmd = [
        "hop3-test",
        "system",
        "--ssh",
        "--host",
        host,
        "--with",
        "all",
        *_suite_args(mode, apps),
        "--report",
        "html",
    ]
    _run_engine(target_id, cmd, env)


def run_once(
    target_id: str = "docker",
    *,
    trigger: str = "cli",
    mode: str = "nightly",
    apps: list[str] | None = None,
    executor: Callable[[str, str, list[str] | None], None] | None = None,
) -> bool:
    """Run the suite once under the target lease.

    ``apps`` scopes the run to specific app paths (a per-app build); otherwise the
    full ``mode`` suite. Returns True if it ran, False if the target is busy (a
    live lease is held). The lease is always released (even if the run raises).
    """
    config = TestlabConfig.get_instance()
    factory = get_session_factory(str(config.DB_PATH))

    session = factory()
    try:
        if not leasing.try_acquire(session, target_id, trigger):
            return False
        # A prior run killed mid-flight (e.g. via the dashboard Stop) or crashed
        # never stamped finished_at; clear such orphans now so they can't
        # masquerade as this run on the dashboard. v1 runs one suite at a time,
        # so any unfinished row at acquire time predates this lease.
        RunsRepository(session).sweep_orphans()
    finally:
        session.close()

    try:
        # Tag the run via env so the spawned engine's start_run records the
        # provenance (scheduled-nightly vs cli) on the TestRun (ADR 044 §D).
        prev = os.environ.get("HOP3_TEST_TRIGGER")
        os.environ["HOP3_TEST_TRIGGER"] = trigger
        try:
            (executor or _default_executor)(target_id, mode, apps)
        finally:
            if prev is None:
                os.environ.pop("HOP3_TEST_TRIGGER", None)
            else:
                os.environ["HOP3_TEST_TRIGGER"] = prev
    finally:
        session = factory()
        try:
            leasing.release(session, target_id, trigger)
        finally:
            session.close()
    return True
