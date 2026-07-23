# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
run_captured must surface output even when a grandchild holds the pipe.

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
from hop3_testing.targets.base import TargetInfo
from hop3_testing.util import run_captured
from hop3_testing.util.subprocess import build_test_env


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
    """
    A backgrounded grandchild inherits the pipe and outlives the child.

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


def test_stdin_is_closed_so_a_prompt_cannot_hang():
    """
    A command that reads stdin must get immediate EOF, not block.

    This is the tutorial-hang guard: validoc runs `hop3 deploy`, whose
    ADR-042 confirm prompt reads stdin. With stdin inherited from a tty it
    blocked until the per-command timeout; run_captured pins stdin to
    /dev/null so the read returns EOF at once. `cat` with no file echoes
    stdin, so a closed stdin makes it exit 0 promptly.
    """
    start = time.monotonic()
    result = run_captured(["cat"], timeout=10)
    assert result.returncode == 0
    assert time.monotonic() - start < 5  # would be a 10s timeout if stdin blocked


def test_build_test_env_requests_non_interactive():
    """
    The harness opts every CLI command into non-interactive mode so a
    deploy/confirm prompt can't wedge a tutorial run (HOP3_NO_INPUT bridge).
    """
    env = build_test_env(TargetInfo(ssh_host="h", ssh_port=22))
    assert env["HOP3_NO_INPUT"] == "1"


def test_build_test_env_defaults_test_domain_to_sslip(monkeypatch):
    """
    Tutorials set HOST_NAME=<app>.$HOP3_TEST_DOMAIN and curl it, so the domain
    must resolve to the target. Default to <host>.sslip.io (wildcard public DNS)
    so it works with zero DNS setup; an explicit env value wins.
    """
    monkeypatch.delenv("HOP3_TEST_DOMAIN", raising=False)
    env = build_test_env(TargetInfo(ssh_host="135.181.203.156", ssh_port=22))
    assert env["HOP3_TEST_DOMAIN"] == "135.181.203.156.sslip.io"

    monkeypatch.setenv("HOP3_TEST_DOMAIN", "test.example.com")
    env = build_test_env(TargetInfo(ssh_host="135.181.203.156", ssh_port=22))
    assert env["HOP3_TEST_DOMAIN"] == "test.example.com"  # operator override wins
