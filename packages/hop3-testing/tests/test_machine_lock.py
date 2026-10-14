# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""One e2e session per machine: a second Docker run is refused, loudly."""

from __future__ import annotations

import os

import pytest
from hop3_testing.targets.machine_lock import MachineBusyError, hold_docker_target


def test_a_second_run_is_refused_naming_the_first(tmp_path):
    lock = tmp_path / "docker-target.lock"
    first = hold_docker_target(lock)

    with pytest.raises(MachineBusyError, match=f"pid {os.getpid()}"):
        hold_docker_target(lock)

    first.close()
    hold_docker_target(lock).close()  # released: the next run may start
