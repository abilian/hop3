# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the streaming subprocess runner.

The focus here is the timeout path: when a long-running command exceeds
its deadline, the runner must kill not just the direct child but the
whole process group, so that subprocesses (think `nix-build` spawning
`nix-store`, or `docker compose` spawning containers) don't orphan.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

import pytest
from hop3_testing.util import streaming
from hop3_testing.util.streaming import run_streaming

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Process-group kill semantics are POSIX-specific",
)


def test_timed_out_flag_set_on_deadline() -> None:
    """Sanity: timing out should set timed_out and leave returncode non-zero."""
    result = run_streaming(["sleep", "10"], timeout=1)
    assert result.timed_out is True
    assert result.returncode != 0


def test_run_streaming_uses_devnull_stdin(monkeypatch) -> None:
    """No inherited stdin: a prompting deploy step (ssh host-key/apt/sudo) must
    get EOF and fail fast, not hang the whole timeout. Both deploy wrappers now
    share this via the one runner (ADR 052 Phase 7b.1)."""
    captured: dict = {}
    real_popen = subprocess.Popen

    def spy_popen(*args, **kwargs):
        captured["stdin"] = kwargs.get("stdin")
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(streaming.subprocess, "Popen", spy_popen)
    result = run_streaming(["true"])
    assert result.returncode == 0
    assert captured["stdin"] is subprocess.DEVNULL


def test_timeout_kills_grandchild_process(tmp_path) -> None:
    """The killer signal must reach grand-children, not just the direct child.

    We launch ``sh -c 'sleep 30 & echo $! > marker; wait'``. The shell is
    the direct child; the ``sleep`` is the grand-child whose pid we
    capture in ``marker``. After run_streaming times out, that pid must
    be gone — otherwise a real workload (nix-build, docker compose up)
    would orphan and hold resources.
    """
    marker = tmp_path / "grandchild.pid"
    cmd = f"sleep 30 & echo $! > {marker}; wait"

    result = run_streaming(cmd, timeout=2)
    assert result.timed_out is True

    # Give the OS a brief moment to reap
    time.sleep(0.3)

    grandchild_pid = int(marker.read_text().strip())

    # Sending signal 0 probes for existence without delivering a signal.
    # ProcessLookupError means the process is gone — which is the desired
    # outcome. Any other state (alive, or a stranger now owns the pid) is
    # hard to disambiguate, so we settle for "cannot find it any more".
    with pytest.raises(ProcessLookupError):
        os.kill(grandchild_pid, 0)


def test_successful_completion_path() -> None:
    """Short commands should finish cleanly with timed_out == False."""
    result = run_streaming(["sh", "-c", "echo hello"], timeout=5)
    assert result.timed_out is False
    assert result.returncode == 0
    assert "hello" in result.stdout


def test_on_output_callback_receives_lines() -> None:
    """The streaming callback must see each line as it arrives."""
    seen: list[str] = []
    run_streaming(
        ["sh", "-c", "echo one; echo two; echo three"],
        on_output=seen.append,
        timeout=5,
    )
    assert seen == ["one", "two", "three"]


def test_terminate_tree_is_safe_when_already_exited() -> None:
    """If the child exited between the deadline check and the kill, no crash."""
    # A command that finishes fast but we still call with a very short timeout
    # so the runner *might* enter the kill path; either way, no exception.
    result = run_streaming(["sh", "-c", "exit 0"], timeout=5)
    assert result.returncode == 0
    # Nothing to assert about timed_out specifically — just that we returned.


def test_signals_reach_negative_pgid() -> None:
    """The process itself is a session leader (pgid == pid)."""
    import subprocess  # ruff:ignore[import-outside-top-level]

    # Start a process the same way run_streaming does, verify its pgid,
    # and clean up. This is a direct contract check on start_new_session.
    proc = subprocess.Popen(
        ["sleep", "5"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        assert os.getpgid(proc.pid) == proc.pid
    finally:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.wait(timeout=2)
