# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Robust detection and reaping of an app's runtime processes.

The hard case is a daemon that ``exec``s into a path outside the app dir — a
Nix-store binary becomes argv ``/nix/store/.../bin/owncast``, so ``pgrep -f
apps/<name>`` misses it, yet it keeps holding a fixed host port (e.g. owncast's
RTMP 1935). We match on cmdline AND working directory, and *confirm* processes
are gone (force-killing stragglers) rather than trust that removing a uWSGI
``.ini`` reaped them.

Shared by the uWSGI deployer and the ORM teardown (``app.stop()`` / ``destroy``)
so an explicit ``hop3 app stop`` / ``destroy`` is as thorough as a redeploy —
without this, those commands only removed the Emperor config and reported
STOPPED while the daemon (and its port) lived on.

We reap only *runtime* processes — the uWSGI Emperor's children (the Emperor is
a separate systemd/supervisord service, a distinct process tree). We must never
reap a *build*: a local ``bundle install`` / ``lein uberjar`` runs with cwd
``apps/<name>/src`` and so matches by cwd, but it is a subprocess of
``hop3-server``. Reaping it SIGTERMs the deploy's own build mid-flight (a slow
native compile / Maven fetch outlives the grace and dies with signal 15). The
deploy tree — ancestors, self, and build descendants — is excluded; see
:func:`_protected_pids` and :func:`_is_deploy_descendant`.
"""

from __future__ import annotations

import os
import signal
import time
from contextlib import suppress
from pathlib import Path

from hop3.lib import log

# Grace period after the Emperor stops a vassal before we force-kill leftovers.
GRACEFUL_STOP_SECONDS = 10.0


def proc_belongs_to_app(cmdline: str, cwd: str, app_name: str) -> bool:
    """
    Whether a process (by its cmdline + cwd) belongs to ``app_name``.

    Robust to the two cases plain ``pgrep -f apps/<name>`` gets wrong:

    - A daemon that ``exec``s into a path outside the app dir (a Nix-store
      binary becomes argv ``/nix/store/.../bin/owncast``) — its cmdline no
      longer mentions the app, but its working directory still does.
    - Name-prefix collisions: ``owncast-12`` must not match ``owncast-123``;
      the trailing ``/`` and ``:`` markers enforce a boundary.

    Matches the uWSGI vassal/workers by their procname prefix ``<name>:`` and
    the app's own processes by ``apps/<name>/`` in the cmdline or cwd. Never
    matches the shared Emperor (its cwd/cmdline is not under any app dir).
    """
    return (
        f"{app_name}:" in cmdline
        or f"apps/{app_name}/" in cmdline
        or f"apps/{app_name}/" in cwd
    )


def _parent_pid(pid: int) -> int | None:
    """The parent PID of ``pid`` from procfs, or None if unavailable."""
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("PPid:"):
                return int(line.split(":", 1)[1])
    except (OSError, ValueError):
        return None
    return None


def _protected_pids() -> set[int]:
    """
    The current process and all its ancestors — these are never reaped.

    The reaper runs *inside* the operation that asked for it. On a git-push
    redeploy that operation is the tree ``git-receive-pack`` → post-receive hook
    → ``hop3-server git-hook`` → ``do_deploy`` — every member of which runs with
    a cwd under ``apps/<name>/`` and so matches :func:`proc_belongs_to_app` by
    cwd. Without this guard the reaper SIGTERMs its own ancestor
    ``git-receive-pack`` mid-push (the deploy kills the process feeding it the
    pushed code), which aborts the push. A process the reaper is running inside
    is by definition deploy machinery, never an app *runtime* process (those are
    children of the uWSGI Emperor — a separate tree), so excluding self +
    ancestors is always safe.
    """
    protected: set[int] = set()
    pid: int | None = os.getpid()
    while pid and pid not in protected:
        protected.add(pid)
        pid = _parent_pid(pid)
    return protected


def _is_deploy_descendant(pid: int) -> bool:
    """
    Whether ``pid`` descends from the current process.

    A build/deploy subprocess this hop3-server spawned — ``bundle install``,
    ``lein uberjar``, the ``make``/``cc`` children of a native-gem compile — runs
    with cwd ``apps/<name>/src``, so it *matches* :func:`proc_belongs_to_app` by
    cwd. But it is **build machinery, not an app runtime process**: runtime
    processes are the uWSGI Emperor's children (the ``uwsgi-hop3`` systemd unit /
    the supervisord ``uwsgi`` program — a separate tree), never descendants of
    ``hop3-server``. So a matched process that descends from us is the in-flight
    build; reaping it would SIGTERM the deploy's own build (a slow native compile
    or Maven fetch outlives the 10s grace and dies with signal 15). This is the
    descendant counterpart to :func:`_protected_pids`' ancestor guard; together
    they exclude the whole deploy tree (ancestors + self + build children) while
    still reaping every Emperor-supervised runtime process.
    """
    me = os.getpid()
    cur = pid
    for _ in range(128):  # bounded walk; also guards a pathological parent cycle
        parent = _parent_pid(cur)
        if parent is None or parent <= 1:
            return False
        if parent == me:
            return True
        cur = parent
    return False


def app_pids(app_name: str) -> list[int]:
    """
    PIDs of every live process belonging to ``app_name``.

    Scans ``/proc`` and matches each process's cmdline and working directory
    (see :func:`proc_belongs_to_app`). Catches Nix-store ``exec``'d daemons that
    ``pgrep -f apps/<name>`` misses. The reaper's own process tree is excluded —
    its ancestors (so a redeploy never kills the in-flight ``git-receive-pack``
    it runs under, :func:`_protected_pids`) *and* its build/deploy descendants
    (so a reap never SIGTERMs the app's own in-flight build, which shares the
    ``apps/<name>/src`` cwd, :func:`_is_deploy_descendant`). Returns ``[]`` where
    there is no procfs (a non-Linux dev machine), where there is nothing to reap.
    """
    proc = Path("/proc")
    if not proc.is_dir():
        return []
    protected = _protected_pids()
    pids: list[int] = []
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid in protected:
            continue  # never reap ourselves or an ancestor (e.g. git-receive-pack)
        try:
            cmdline = (entry / "cmdline").read_bytes().replace(b"\x00", b" ")
        except OSError:
            continue  # process exited between listing and read
        cwd = ""
        # cwd unreadable (perms/gone) — the cmdline match still applies
        with suppress(OSError):
            cwd = os.readlink(entry / "cwd")
        if not proc_belongs_to_app(cmdline.decode("utf-8", "replace"), cwd, app_name):
            continue
        if _is_deploy_descendant(pid):
            continue  # our own build subprocess (shares the src cwd), not runtime
        pids.append(pid)
    return pids


def reap_app_processes(
    app_name: str, timeout: float = GRACEFUL_STOP_SECONDS
) -> list[int]:
    """
    Block until ``app_name``'s processes are gone, force-killing stragglers.

    Removing a uWSGI ``.ini`` makes the Emperor stop the vassal, which should
    terminate the app's processes — we *confirm* that here rather than guess. A
    leftover daemon binding a fixed port would otherwise make the next deploy of
    that app fail with an opaque 'address already in use' (an order-dependent
    heisenbug). Stragglers that survive the grace period get SIGTERM then
    SIGKILL; by this point the vassal is gone, so nothing respawns them.

    Returns the PIDs that survived even SIGKILL (``[]`` on success), so callers
    can report the actual failure instead of a false STOPPED.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not app_pids(app_name):
            time.sleep(0.5)  # brief grace for fd / port release
            return []
        time.sleep(0.5)

    stragglers = app_pids(app_name)
    if not stragglers:
        return []
    log(
        f"Force-stopping {len(stragglers)} leftover process(es) for "
        f"'{app_name}' (graceful stop timed out)",
        level=2,
        fg="yellow",
    )
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in app_pids(app_name):
            with suppress(OSError):
                os.kill(pid, sig)
        time.sleep(1.0)
    return app_pids(app_name)
