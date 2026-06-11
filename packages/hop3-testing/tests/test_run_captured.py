# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""run_captured must surface output even when a grandchild holds the pipe.

Demo and tutorial runs spawn `hop3`/`ssh` grandchildren that inherit the
captured pipes. Plain ``subprocess.run`` kills only the direct child on
timeout, so a surviving grandchild keeps the pipe open and the post-kill
``communicate()`` wedges — the run never returns and no logs are saved.
``run_captured`` kills the whole process group, so it returns promptly with
whatever was buffered.
"""

from __future__ import annotations

import subprocess
import time

import pytest
from hop3_testing.util import run_captured


def test_completes_and_returns_output():
    result = run_captured(["sh", "-c", "echo hello; echo oops >&2"], timeout=10)
    assert result.returncode == 0
    assert "hello" in result.stdout
    assert "oops" in result.stderr


def test_nonzero_exit_does_not_raise():
    result = run_captured(["sh", "-c", "echo boom; exit 3"], timeout=10)
    assert result.returncode == 3
    assert "boom" in result.stdout


def test_timeout_captures_partial_output():
    with pytest.raises(subprocess.TimeoutExpired) as exc_info:
        run_captured(["sh", "-c", "echo early-output; sleep 60"], timeout=1)
    assert "early-output" in (exc_info.value.output or "")


def test_timeout_kills_group_when_grandchild_holds_pipe():
    """A backgrounded grandchild inherits the pipe and outlives the child.

    Plain subprocess.run would wedge in communicate() for the grandchild's full
    lifetime; run_captured must SIGKILL the whole group and return promptly with
    the buffered output.
    """
    cmd = ["sh", "-c", "sleep 60 & echo started; sleep 60"]
    start = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired) as exc_info:
        run_captured(cmd, timeout=1)
    elapsed = time.monotonic() - start
    assert "started" in (exc_info.value.output or "")
    # Without the process-group kill this would block ~60s on the grandchild.
    assert elapsed < 30, f"run_captured wedged on the grandchild ({elapsed:.1f}s)"
