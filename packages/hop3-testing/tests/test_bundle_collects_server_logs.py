# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
The bundle must collect the server's log from whichever process manager is running.

The journal section used to branch on `command -v journalctl`. That binary is
present in the Docker test image even though nothing there runs under systemd,
so the journalctl path was taken, journalctl replied "No journal files were
found", and the bundle recorded that as the server's log.

An empty section reads as "the server logged nothing", which is the most
misleading answer available. It cost a full day: 34 apps failed on
"Authentication required", the reason the server denied the token was written
to a supervisor log, and the bundle — the thing the failure message tells you
to read — never looked there.

So the branch is on PID 1, and a section that comes back empty says so.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

BUNDLE = Path(__file__).parent.parent / "src" / "hop3_testing" / "bundle.py"


def _journal_command() -> str:
    """The shell the bundle runs to collect the server log."""
    tree = ast.parse(BUNDLE.read_text())
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and node.targets
            and isinstance(node.targets[0], ast.Subscript)
        ):
            key = node.targets[0].slice
            if isinstance(key, ast.Constant) and key.value == "journal":
                return ast.literal_eval(node.value.args[1])
    pytest.fail("no sections['journal'] assignment found in bundle.py")
    return ""


def test_the_collector_is_valid_shell():
    """A collector that does not parse gathers nothing, quietly."""
    command = _journal_command()

    result = subprocess.run(
        ["bash", "-n"], input=command, text=True, capture_output=True, check=False
    )

    assert result.returncode == 0, result.stderr


def test_it_decides_on_pid_1_not_on_a_binary_being_installed():
    command = _journal_command()

    assert "/proc/1/comm" in command
    assert "command -v journalctl" not in command


def test_it_reads_the_supervisor_logs_where_there_is_no_systemd():
    command = _journal_command()

    assert "/var/log/supervisor/hop3-server.log" in command
    assert "/var/log/supervisor/hop3-server_err.log" in command


def test_an_empty_result_is_reported_as_a_gap(tmp_path):
    """
    Running it where no logs exist must say the log could not be collected.

    Silence here is indistinguishable from a healthy server, and that is
    precisely the confusion this section exists to prevent.
    """
    command = _journal_command()

    result = subprocess.run(
        ["bash", "-c", command], capture_output=True, text=True, check=False
    )

    assert "could not be collected" in result.stdout
    assert "NOT evidence that the server logged nothing" in result.stdout
