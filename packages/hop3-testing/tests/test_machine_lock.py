# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""One e2e session per machine: a second Docker run is refused, loudly."""

from __future__ import annotations

import subprocess
import sys

import pytest
from hop3_testing.targets.machine_lock import MachineBusyError, hold_docker_target

_TAKE = (
    "import sys; from pathlib import Path;"
    "from hop3_testing.targets.machine_lock import hold_docker_target;"
    "hold_docker_target(Path(sys.argv[1])); print('held', flush=True);"
    "sys.stdin.read()"
)


def test_a_second_run_is_refused_naming_the_first(tmp_path):
    lock = tmp_path / "docker-target.lock"
    other = subprocess.Popen(
        [sys.executable, "-c", _TAKE, str(lock)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert other.stdout is not None
        assert other.stdout.readline().strip() == "held"
        with pytest.raises(MachineBusyError, match=f"pid {other.pid}"):
            hold_docker_target(lock)
    finally:
        other.communicate("")  # the other run exits: the kernel releases its lock

    hold_docker_target(lock).close()  # released: the next run may start


def test_one_session_takes_it_again_and_keeps_it_until_the_last_close(tmp_path):
    """pytest's session fixture holds the lock, then starts a Docker target."""
    lock = tmp_path / "docker-target.lock"
    session = hold_docker_target(lock)
    target = hold_docker_target(lock)

    target.close()
    probe = [sys.executable, "-c", _TAKE, str(lock)]
    held_elsewhere = subprocess.run(probe, input="", capture_output=True, check=False)
    assert held_elsewhere.returncode != 0  # the session's hold still holds it

    session.close()
    assert subprocess.run(probe, input="", check=False).returncode == 0
