# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
The reaper against a *real* process tree — no mocks.

The a_unit reaper tests monkeypatch ``proc_belongs_to_app`` /
``_is_deploy_descendant`` and stub ``os.kill`` / ``time.sleep``, so they pin the
logic but never touch a live ``/proc`` scan or a real kill. These do: they spawn
actual processes and assert the two invariants that keep native teardown honest —

- a detached daemon (reparented to init, argv no longer mentioning the app, like
  a Nix-``exec``'d binary) is found by cwd and *actually killed*; and
- an in-flight build (a subprocess of this deploy, sharing ``apps/<name>/src``)
  is spared, so a redeploy never SIGTERMs its own build.

Reaping reads ``/proc``, so this is Linux-only; it skips where there is none.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from contextlib import suppress
from pathlib import Path

import pytest

from hop3.run.reaper import (
    _is_deploy_descendant,
    app_pids,
    proc_belongs_to_app,
    reap_app_processes,
)

pytestmark = pytest.mark.skipif(
    not Path("/proc").is_dir(), reason="the reaper scans /proc (Linux-only)"
)


def _wait_until_gone(pid: int, timeout: float = 3.0) -> bool:
    """True once ``pid`` is no longer a live process (init reaps the zombie)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False  # exists but not ours — treat as still alive
        time.sleep(0.05)
    return False


def _spawn_detached_daemon(cwd: Path) -> int:
    """
    Start ``sleep`` reparented to init — NOT a descendant of this test process.

    Double-fork so the grandchild's parent (the first child) exits immediately
    and the kernel reparents the grandchild to init. That is the exec'd-daemon
    shape the reaper must catch: it belongs to the app by *cwd* but its ancestry
    never passes through us, so the deploy-descendant guard does not spare it.
    """
    read_fd, write_fd = os.pipe()
    first = os.fork()
    if first == 0:  # first child
        os.close(read_fd)
        os.setsid()
        grandchild = os.fork()
        if grandchild == 0:  # the daemon
            os.close(write_fd)
            os.chdir(cwd)
            os.execvp("sleep", ["sleep", "300"])
            os._exit(127)  # only reached if exec fails
        os.write(write_fd, str(grandchild).encode())
        os.close(write_fd)
        os._exit(0)  # first child exits -> grandchild reparents to init
    os.close(write_fd)
    os.waitpid(first, 0)  # reap the first child
    pid = int(os.read(read_fd, 32).decode())
    os.close(read_fd)
    return pid


def _app_tree(tmp_path: Path, name: str) -> Path:
    """The ``apps/<name>/src`` cwd a runtime process (and a build) run under."""
    src = tmp_path / "apps" / name / "src"
    src.mkdir(parents=True)
    return src


def test_reaps_a_detached_app_daemon(tmp_path):
    """A daemon that isn't our child is found by cwd and actually killed."""
    name = f"reapit-{os.getpid()}"
    src = _app_tree(tmp_path, name)

    pid = _spawn_detached_daemon(src)
    try:
        os.kill(pid, 0)  # precondition: it really started
        assert not _is_deploy_descendant(pid), "daemon must not descend from us"
        assert pid in app_pids(name), "reaper must find it by its cwd"

        # timeout=0 skips the graceful wait and goes straight to SIGTERM/SIGKILL.
        survivors = reap_app_processes(name, timeout=0.0)

        assert survivors == []
        assert app_pids(name) == []
        assert _wait_until_gone(pid), "the daemon's process must be gone"
    finally:
        with suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)


def test_spares_an_in_flight_build_subprocess(tmp_path):
    """A build subprocess of ours shares the app cwd but must never be reaped."""
    name = f"buildit-{os.getpid()}"
    src = _app_tree(tmp_path, name)

    # A direct child, like `bundle install` under a deploy: it shares apps/<name>/src.
    build = subprocess.Popen(["sleep", "60"], cwd=str(src))
    try:
        build_cwd = os.readlink(f"/proc/{build.pid}/cwd")
        # It genuinely looks like the app...
        assert proc_belongs_to_app("sleep 60", build_cwd, name)
        assert _is_deploy_descendant(build.pid)
        # ...yet is spared, because reaping it would kill the deploy's own build.
        assert build.pid not in app_pids(name)
        assert build.poll() is None, "the build subprocess must still be alive"
    finally:
        build.kill()
        build.wait()
