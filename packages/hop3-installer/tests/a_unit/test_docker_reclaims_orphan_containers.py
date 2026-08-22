# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
A killed run must not block the next one.

A run stopped by Ctrl-C, a timeout or the OOM killer cannot tear its own
container down, and that container goes on holding host ports 8000/8080/8443.
The next run fails before it starts — and it need not even be the same harness:
`hop3-test` uses `hop3-system-test` while the pytest e2e layer uses
`hop3-server-test`, different names competing for the same three ports. The only
cure was a hand-typed `docker rm -f`.

That is the shape the project forbids: a leftover that blocks the next deploy is
a platform bug, and the fix does not get to be "tell the operator to run a
command".

So containers are stamped with the pid that created them, and a conflicting one
is reclaimed only when that pid is gone. A live run's container is somebody's
work in progress; taking it away would be worse than the conflict it resolves.
"""

from __future__ import annotations

import os
from unittest.mock import patch

from hop3_installer.deployer.backends.docker import (
    MARKER_LABEL,
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
    assert f"{MARKER_LABEL}=1" in argv


def test_the_labels_precede_the_image():
    """A flag after the image name is an argument to the command, not to docker."""
    argv = _run_argv()

    assert argv.index(f"{OWNER_LABEL}={os.getpid()}") < argv.index("sleep")


def test_an_orphan_of_ours_is_reclaimed():
    backend = _backend()
    conflicts = [(8000, "hop3-system-test", "Hop3 API")]
    removed: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        if argv[:2] == ["docker", "inspect"]:
            return type("R", (), {"returncode": 0, "stdout": "999999\n"})()
        removed.append(argv)
        return type("R", (), {"returncode": 0, "stdout": ""})()

    with patch("subprocess.run", side_effect=fake_run):
        reclaimed = backend._reclaim_orphans(conflicts)

    assert reclaimed == ["hop3-system-test"]
    assert ["docker", "rm", "-f", "hop3-system-test"] in removed


def test_a_container_belonging_to_a_live_run_is_left_alone():
    """Somebody is using it. Reporting the conflict beats stealing their box."""
    backend = _backend()
    conflicts = [(8000, "hop3-system-test", "Hop3 API")]
    removed: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        if argv[:2] == ["docker", "inspect"]:
            return type("R", (), {"returncode": 0, "stdout": f"{os.getpid()}\n"})()
        removed.append(argv)
        return type("R", (), {"returncode": 0, "stdout": ""})()

    with patch("subprocess.run", side_effect=fake_run):
        reclaimed = backend._reclaim_orphans(conflicts)

    assert reclaimed == []
    assert removed == []


def test_a_container_that_is_not_ours_is_never_touched():
    """No label: someone else's container, or one from an older build."""
    backend = _backend()
    conflicts = [(8000, "someones-postgres", "Hop3 API")]
    removed: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        if argv[:2] == ["docker", "inspect"]:
            return type("R", (), {"returncode": 0, "stdout": "<no value>\n"})()
        removed.append(argv)
        return type("R", (), {"returncode": 0, "stdout": ""})()

    with patch("subprocess.run", side_effect=fake_run):
        reclaimed = backend._reclaim_orphans(conflicts)

    assert reclaimed == []
    assert removed == []


def test_a_recycled_pid_errs_toward_reporting_the_conflict():
    """Wrong in the safe direction: the old manual behaviour, not a wrong delete."""
    assert _process_is_alive(str(os.getpid())) is True
    assert _process_is_alive("999999") is False
    assert _process_is_alive("not-a-pid") is False
