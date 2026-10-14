# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
A killed run must not leave its container behind.

A run stopped by Ctrl-C, a timeout or the OOM killer cannot tear its own
container down. It held the fixed host ports, so the next run failed before it
started and only a hand-typed `docker rm -f` cleared it; with ports Docker
picks, it holds the Docker host's memory and disk instead.

That is the shape the project forbids: a leftover is a platform bug, and the fix
does not get to be "tell the operator to run a command".

So containers are stamped with the machine and the pid that created them, and
one is reclaimed only when it was created here and that pid is gone. A live
run's container is somebody's work in progress, and a pid from another machine
that shares the Docker host says nothing about this one.
"""

from __future__ import annotations

import os
import socket
from unittest.mock import patch

from hop3_installer.deployer.backends.docker import (
    MARKER_LABEL,
    OWNER_HOST_LABEL,
    OWNER_LABEL,
    DockerDeployBackend,
    _process_is_alive,
)
from hop3_installer.deployer.config import DeployConfig


def _backend() -> DockerDeployBackend:
    return DockerDeployBackend(DeployConfig(use_docker=True))


def _run_argv() -> list[str]:
    backend = _backend()
    with patch("subprocess.run") as run:
        run.return_value.returncode = 0
        backend._start_container()
        return list(run.call_args[0][0])


def test_containers_record_the_run_that_created_them():
    argv = _run_argv()

    assert f"{OWNER_LABEL}={os.getpid()}" in argv
    assert f"{OWNER_HOST_LABEL}={socket.gethostname()}" in argv
    assert f"{MARKER_LABEL}=1" in argv


def test_no_host_port_is_fixed():
    """A fixed host port collides with whatever else the Docker host runs."""
    argv = _run_argv()

    published = [a for a in argv if a.startswith("--publish=")]
    assert published == ["--publish=8000", "--publish=80", "--publish=443"]


def test_the_labels_precede_the_image():
    """A flag after the image name is an argument to the command, not to docker."""
    argv = _run_argv()

    assert argv.index(f"{OWNER_LABEL}={os.getpid()}") < argv.index("sleep")


def _reclaim(*, listed: str, owner: str) -> tuple[list[str], list[list[str]]]:
    """Run `_reclaim_orphans` against a daemon that lists ``listed``."""
    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        calls.append(argv)
        stdout = {"ps": listed, "inspect": owner}.get(argv[1], "")
        return type("R", (), {"returncode": 0, "stdout": stdout})()

    with patch("subprocess.run", side_effect=fake_run):
        reclaimed = _backend()._reclaim_orphans()
    return reclaimed, calls


def test_an_orphan_of_ours_is_reclaimed():
    reclaimed, calls = _reclaim(listed="hop3-system-test\n", owner="999999\n")

    assert reclaimed == ["hop3-system-test"]
    assert ["docker", "rm", "-f", "hop3-system-test"] in calls


def test_only_containers_labelled_from_this_machine_are_listed():
    _, calls = _reclaim(listed="", owner="")

    (ps,) = [argv for argv in calls if argv[1] == "ps"]
    assert f"label={MARKER_LABEL}" in ps
    assert f"label={OWNER_HOST_LABEL}={socket.gethostname()}" in ps


def test_a_container_belonging_to_a_live_run_is_left_alone():
    """Somebody is using it."""
    reclaimed, calls = _reclaim(listed="hop3-system-test\n", owner=f"{os.getpid()}\n")

    assert reclaimed == []
    assert not [argv for argv in calls if argv[1] == "rm"]


def test_a_container_without_an_owner_is_never_touched():
    """An older build's container: no pid to judge it by."""
    reclaimed, calls = _reclaim(listed="hop3-system-test\n", owner="<no value>\n")

    assert reclaimed == []
    assert not [argv for argv in calls if argv[1] == "rm"]


def test_a_recycled_pid_errs_toward_keeping_the_container():
    """Wrong in the safe direction: a leftover, not a wrong delete."""
    assert _process_is_alive(str(os.getpid())) is True
    assert _process_is_alive("999999") is False
    assert _process_is_alive("not-a-pid") is False
