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
import logging
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING

from hop3_testing.targets.helpers import find_project_root

from hop3_testlab import leasing
from hop3_testlab.catalog import build_catalog, resolve_selector
from hop3_testlab.cloud_config import load_cloud_config
from hop3_testlab.config import TestlabConfig
from hop3_testlab.db import get_session_factory
from hop3_testlab.repositories import RunsRepository
from hop3_testlab.selection import resolve_selection

if TYPE_CHECKING:
    from collections.abc import Callable

    from hop3_testlab.cloud_config import CloudConfig
    from hop3_testlab.sources import Source

STOP_GRACE_SECONDS = 5.0

logger = logging.getLogger(__name__)


def _hetzner_manager(cfg: CloudConfig):
    """Build a HetznerManager from the cloud config (lazy: hcloud is heavy).

    Carries both ``ssh_key_name`` and ``ssh_key_path`` so the rebuild can resolve
    the registered key explicitly, or auto-derive it from the local key.
    """
    from hop3_testing.system_tests.config import HetznerConfig  # noqa: PLC0415
    from hop3_testing.system_tests.hetzner import HetznerManager  # noqa: PLC0415

    return HetznerManager(
        HetznerConfig(
            api_token=cfg.hetzner_token,
            server_id=cfg.hetzner_server_id,
            image=cfg.hetzner_image,
            ssh_key_name=cfg.hetzner_ssh_key_name,
            ssh_key_path=cfg.ssh_key_path,
        )
    )


def _hetzner_server_info(cfg: CloudConfig):
    """Fetch the configured Hetzner server's info."""
    return _hetzner_manager(cfg).get_server_info()


def _resolve_hetzner_ssh_key(cfg: CloudConfig) -> None:
    """Validate that the rebuild can resolve an SSH key to re-inject.

    Raises (loud, explained) if it can't — used by ``run_blockers`` as a
    pre-flight so the web trigger refuses up-front instead of spawning a run
    that aborts unseen.
    """
    _hetzner_manager(cfg).resolve_ssh_key()


def _rebuild_blank_slate(cfg: CloudConfig) -> None:
    """Rebuild the Hetzner server to a fresh OS before a full-suite run.

    This is what makes runs reproducible: each run starts from an identical,
    known state instead of inheriting leaked apps/addons/disk from prior runs.
    The rebuild re-injects an SSH key so we keep access — resolved explicitly
    (hetzner.ssh_key_name) or auto-derived from [ssh] key_path. If no key can be
    resolved, ``rebuild_server`` aborts loudly rather than silently skipping (a
    skipped rebuild is how prior runs' test apps piled up for days).
    """
    manager = _hetzner_manager(cfg)
    print(
        f"[blank-slate] rebuilding Hetzner server {cfg.hetzner_server_id} "
        f"with {cfg.hetzner_image} ..."
    )
    manager.rebuild_server(image=cfg.hetzner_image, timeout=600)
    if not manager.wait_for_ssh_ready(timeout=300):
        msg = "Blank-slate rebuild: SSH never became ready after rebuild"
        raise RuntimeError(msg)
    print("[blank-slate] server rebuilt; SSH ready")


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


def run_blockers(target_id: str, apps: list[str] | None) -> str | None:
    """A human reason this run can't start cleanly, or None if it can.

    Lets the web trigger refuse up-front with a visible message instead of
    spawning a detached run that aborts where the user never sees it. A
    full-suite hetzner run rebuilds the OS first, which must be able to re-inject
    an SSH key (explicit name, or auto-derived from [ssh] key_path); we verify
    that against the Hetzner project here so a missing/unregistered key surfaces
    at click-time rather than as a doomed background run.
    """
    if target_id == "hetzner" and not apps:
        try:
            _resolve_hetzner_ssh_key(load_cloud_config())
        except Exception as e:  # surface the real reason to the UI
            return f"Can't start: {e}"
    return None


def _proc_starttime(pid: int) -> int | None:
    """The process start-time (jiffies since boot, ``/proc/<pid>/stat`` field 22).

    A reuse-proof identity for the engine PID: the kernel never reissues the same
    (pid, starttime) pair. Returns None when unreadable (process gone, or no
    procfs — e.g. a macOS dev machine), in which case identity can't be checked.
    """
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
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
    factory = get_session_factory(config.STORE_TARGET)
    session = factory()
    try:
        leasing.set_pid(session, target_id, pid, _proc_starttime(pid))
    finally:
        session.close()


def _run_engine(
    target_id: str, cmd: list[str], env: dict | None, cwd: Path | None = None
) -> None:
    """Spawn the engine in its OWN session (killable as a process group) and wait.

    ``start_new_session=True`` makes the engine a session/group leader, so the
    dashboard's stop control can ``os.killpg`` the whole run (engine + the docker/
    ssh children it spawns) without touching this worker or the web app. We record
    the PID on the lease right after spawn, then block until it exits. ``cwd`` is
    the fetched ``source@ref`` workspace the engine resolves apps against (None =
    the engine's own project root).
    """
    # Tee the engine's combined output to a per-run breadcrumb log instead of
    # letting it inherit (and vanish into) the worker's stdout: a run that dies
    # in setup (bad deploy, refused blank-slate) before recording any row would
    # otherwise leave nothing the user can look at. Restores `hop3-testlab logs`.
    log_path = _engine_log_path(env)
    with log_path.open("w") as log:
        proc = subprocess.Popen(
            cmd,
            start_new_session=True,
            env=env,
            cwd=cwd,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        # Recording the PID is best-effort — never abort the run — but a failure
        # silently disables the Stop control, so make it visible (#5).
        try:
            _record_engine_pid(target_id, proc.pid)
        except Exception as e:
            logger.warning(
                "Could not record engine PID; Stop control disabled for this run: %s",
                e,
            )
        returncode = proc.wait()
    if returncode != 0:
        # Fail loud (NON-NEGOTIABLE): a non-zero engine exit is a *failed* build.
        # Raise with the log path + tail so run_once propagates it, the dispatcher
        # records the build FAILED **with the real reason** (BuildRequest.detail),
        # and the CLI exits non-zero — never a green build for a failed run.
        tail = _tail_of(log_path)
        msg = f"Engine exited {returncode}. Last output ({log_path}):\n{tail}"
        raise RuntimeError(msg)


def _engine_log_path(env: dict | None) -> Path:
    """A per-run log file under ``~/.hop3/testlab-logs/`` named by trigger+stamp."""
    trigger = (env or os.environ).get("HOP3_TEST_TRIGGER") or "run"
    log_dir = Path.home() / ".hop3" / "testlab-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe = trigger.replace("/", "_").replace(":", "_")
    return log_dir / f"{safe}-{stamp}.log"


def _tail_of(path: Path, lines: int = 25) -> str:
    """The last ``lines`` of a log file (for an actionable failure detail)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        return "\n".join(text.splitlines()[-lines:])
    except OSError:
        return "(no output captured)"


def _runner_version() -> str:
    """Version of the test engine (``hop3-testing``) driving this run."""
    try:
        return version("hop3-testing")
    except PackageNotFoundError:
        return "unknown"


def _default_executor(  # noqa: PLR0913 — same composition inputs as run_once; → RunSpec in slice 2
    target_id: str,
    mode: str,
    apps: list[str] | None,
    *,
    platform_ref: str | None = None,
    cwd: Path | None = None,
    provenance: dict[str, str] | None = None,
    blank_slate: bool = False,
) -> None:
    """Run the suite via the existing engine (results -> shared store).

    ``--with all`` installs every addon feature (mysql/postgresql/redis/nix/…) so
    addon-dependent apps can provision; without it they fail at deploy time
    ("addon can't provision … re-run with --with <feature>"). ``apps`` scopes the
    run to specific app paths (a per-app build); otherwise the full mode suite.

    ``platform_ref`` selects the hop3 ref the engine installs (``--branch``); ``cwd``
    is the fetched ``source@ref`` workspace the engine scans/deploys from — so apps
    and platform can be different refs (v2 spec §A). ``provenance`` (the run's
    composition identity) and any per-target session details are merged into
    ``HOP3_TEST_META``, which ``ResultStore.start_run`` records on the run.
    """
    branch = ["--branch", platform_ref] if platform_ref else []
    meta = dict(provenance or {})
    env = dict(os.environ)
    # The engine subprocess must write to the SAME store the Lab reads — its
    # ResultStore() default is the local SQLite file, which diverges from a
    # Postgres / custom STORE_TARGET and makes results silently invisible (#4).
    env["HOP3_TEST_RESULTS_DB"] = str(TestlabConfig.get_instance().STORE_TARGET)

    if target_id in {"docker", ""}:
        if meta:
            env["HOP3_TEST_META"] = json.dumps(meta)
        cmd = [
            "hop3-test",
            "system",
            "--docker",
            "--with",
            "all",
            *branch,
            *_suite_args(mode, apps),
            "--report",
            "html",
        ]
        _run_engine(target_id, cmd, env, cwd)
        return

    host, ssh_key, session_meta = _resolve_run_target(target_id)
    meta.update(session_meta)  # session details join the provenance in run_metadata

    # Blank slate for reproducibility: rebuild the Hetzner OS before a clean run
    # so every run starts from an identical, known state. Driven by explicit
    # intent (`blank_slate`), not by `not apps` — a v2 dispatched/nightly profile
    # build always resolves a concrete apps list, so the old heuristic silently
    # skipped the rebuild on the canonical path (#2/#7). Ad-hoc per-app re-runs
    # leave it False and test against the live server.
    if target_id == "hetzner" and blank_slate:
        _rebuild_blank_slate(load_cloud_config())

    if ssh_key:
        env["HOP3_TEST_SSH_KEY"] = ssh_key
    if meta:
        env["HOP3_TEST_META"] = json.dumps(meta)
    cmd = [
        "hop3-test",
        "system",
        "--ssh",
        "--host",
        host,
        "--with",
        "all",
        *branch,
        *_suite_args(mode, apps),
        "--report",
        "html",
    ]
    _run_engine(target_id, cmd, env, cwd)


@dataclass(frozen=True, slots=True)
class RunSpec:
    """What to build (v2 spec §A): a run's composition inputs.

    Apps are resolved against the fetched ``source@source_ref`` workspace, in
    precedence: a profile's ``selection`` rules (via the engine `Selector`), an
    ad-hoc glob ``selector``, or a pre-resolved ``apps`` list. ``platform_ref``
    picks the hop3 ref the engine installs (``--branch``). An empty spec is a
    legacy local run (the whole ``mode`` suite on the local checkout).
    """

    source: Source | None = None
    source_ref: str | None = None
    platform_ref: str | None = None
    selector: str | None = None
    selection: dict | None = None
    apps: list[str] | None = None
    # Rebuild the Hetzner OS first (reproducible clean run). Set by the dispatcher
    # for queued/nightly profile builds; False for ad-hoc per-app re-runs.
    blank_slate: bool = False


def _require_nonempty(apps: list[str] | None, what: str) -> None:
    """Fail loud: an empty resolution must not fall through to the full mode
    suite (``_suite_args`` treats ``[]`` as "no apps" → the whole mode)."""
    if not apps:
        msg = f"No apps matched {what}."
        raise ValueError(msg)


def _compose_inputs(
    spec: RunSpec,
) -> tuple[list[str] | None, Path | None, dict[str, str]]:
    """Resolve a run's composition: fetch ``source@source_ref`` into a workspace,
    resolve the apps against it, and build the provenance dict.

    Returns ``(apps, cwd, provenance)`` — ``cwd`` the workspace the engine runs
    from, ``provenance`` the run's composition identity for ``run_metadata``.
    """
    apps = spec.apps
    provenance: dict[str, str] = {"runner_version": _runner_version()}
    if spec.platform_ref:
        provenance["platform_ref"] = spec.platform_ref

    if spec.source is not None and not spec.source_ref:
        # Fail loud: a source with a blank ref must NOT silently fall through to
        # the full local suite against the wrong tree.
        msg = f"source {spec.source.name!r} given without a source_ref"
        raise ValueError(msg)

    cwd: Path | None
    if spec.source is not None and spec.source_ref:
        cwd = spec.source.fetch(spec.source_ref)
        at = f"{spec.source.name}@{spec.source_ref}"
        provenance["source_name"] = spec.source.name
        provenance["apps_ref"] = spec.source_ref
        if spec.selection is not None:
            apps = resolve_selection(build_catalog(cwd), spec.selection)
            _require_nonempty(apps, f"selection in {at}")
        elif spec.selector:
            apps = resolve_selector(cwd, spec.selector)
            _require_nonempty(apps, f"selector {spec.selector!r} in {at}")
    else:
        # Legacy/local run (no source): run the engine from the repo root so it
        # finds the apps/ tree. The Lab's own cwd may be the testlab package
        # (which has no apps), which makes the engine's default scan abort.
        cwd = find_project_root()
    return apps, cwd, provenance


def run_once(
    target_id: str = "docker",
    *,
    trigger: str = "cli",
    mode: str = "nightly",
    spec: RunSpec | None = None,
    executor: Callable[..., None] | None = None,
) -> bool:
    """Run the suite once under the target lease.

    ``spec`` (a :class:`RunSpec`) carries the composition inputs — source/ref to
    fetch, the platform ref to install, and how to pick apps (selection rules,
    a glob, or a pre-resolved list). An absent spec is the legacy ``mode`` suite
    on the local checkout.

    Returns True if it ran, False if the target is busy (a live lease is held). The
    lease is always released (even if fetch or the run raises).
    """
    spec = spec or RunSpec()
    config = TestlabConfig.get_instance()
    factory = get_session_factory(config.STORE_TARGET)

    session = factory()
    try:
        if not leasing.try_acquire(session, target_id, trigger):
            return False
        # A prior run killed mid-flight (e.g. via the dashboard Stop) or crashed
        # never stamped finished_at; clear such orphans now so they can't
        # masquerade as this run on the dashboard.
        # ponytail: skip the sweep when another target's lease is live — the
        # sweep is unscoped, so it would abort that healthy run (#2). Safe to
        # skip: its orphan (if any) is cleared at the next idle sweep. A
        # per-target scoped sweep arrives with parallel dispatch.
        if not leasing.others_live(session, target_id):
            RunsRepository(session).sweep_orphans()
    finally:
        session.close()

    try:
        apps, cwd, provenance = _compose_inputs(spec)

        # Tag the run via env so the spawned engine's start_run records the
        # provenance (scheduled-nightly vs cli) on the TestRun (ADR 044 §D).
        prev = os.environ.get("HOP3_TEST_TRIGGER")
        os.environ["HOP3_TEST_TRIGGER"] = trigger
        try:
            (executor or _default_executor)(
                target_id,
                mode,
                apps,
                platform_ref=spec.platform_ref,
                cwd=cwd,
                provenance=provenance,
                blank_slate=spec.blank_slate,
            )
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
