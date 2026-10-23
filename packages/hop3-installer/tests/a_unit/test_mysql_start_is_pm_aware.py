# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Service control must respect the init system that is actually running.

`_start_mysql_service` ran `systemctl start mysql`, then `systemctl start
mariadb`, and returned False when both failed — which is what happens on every
Docker target, where PID 1 is not systemd. The installer then aborted with
"Could not start MySQL service", two steps after PostgreSQL had started fine
through its own non-systemd path in the same run.

Redis had the same shape and worse consequences: both its calls passed
`check=False`, so on a container they did nothing and said nothing, and the
failure surfaced much later as a connection error in whichever app had declared
a redis addon.

One helper now, `control_service`, rather than a copy per service — this is the
third time a hardcoded `systemctl` has silently no-opped on the Docker target
(see also the deployer's `service_restart_command`).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from hop3_installer import common
from hop3_installer.common import CommandError, InstallStepError, control_service
from hop3_installer.server_installer import mysql, redis


@pytest.fixture
def commands():
    """Record every command run, reporting success for all of them."""
    recorded: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        recorded.append(list(cmd))
        return type("R", (), {"returncode": 0, "stderr": "", "stdout": ""})()

    with patch.object(common, "run_cmd", side_effect=fake_run):
        yield recorded


def test_systemd_hosts_use_systemctl(commands):
    with patch.object(common, "has_systemd", return_value=True):
        control_service("start", "mysql", "mariadb")

    assert commands == [["systemctl", "start", "mysql"]]


def test_a_container_uses_the_init_script(commands):
    """The branch that did not exist. `systemctl` is not even attempted."""
    with (
        patch.object(common, "has_systemd", return_value=False),
        patch.object(Path, "is_file", return_value=True),
    ):
        control_service("start", "mysql", "mariadb")

    assert commands == [["/etc/init.d/mysql", "start"]]
    assert not any("systemctl" in c for c in commands)


def test_the_second_name_is_tried_when_the_first_has_no_script(commands):
    with (
        patch.object(common, "has_systemd", return_value=False),
        patch.object(Path, "is_file", lambda self: self.name == "mariadb"),
    ):
        control_service("start", "mysql", "mariadb")

    assert commands == [["/etc/init.d/mariadb", "start"]]


def test_no_init_script_at_all_is_a_failure(commands):
    """Not a silent success: the install stops, naming the services tried."""
    with (
        patch.object(common, "has_systemd", return_value=False),
        patch.object(Path, "is_file", return_value=False),
        pytest.raises(InstallStepError, match="no init script for mysql"),
    ):
        control_service("start", "mysql")

    assert commands == []


def test_a_failed_systemctl_carries_its_output():
    """
    It returned False, and the caller aborted with "Redis did not restart"
    and nothing else: no stderr, no journal.
    """

    def fake_run(cmd, *args, **kwargs):
        if cmd[0] == "journalctl":
            return type(
                "R", (), {"returncode": 0, "stdout": "journal tail", "stderr": ""}
            )()
        return type("R", (), {"returncode": 1, "stdout": "", "stderr": "unit failed"})()

    with (
        patch.object(common, "has_systemd", return_value=True),
        patch.object(common, "run_cmd", side_effect=fake_run),
        pytest.raises(CommandError) as raised,
    ):
        control_service("restart", "redis-server", "redis")

    assert "systemctl restart redis-server: unit failed" in raised.value.stderr
    assert raised.value.stdout == "journal tail"


def test_mysql_prefers_mysql_then_mariadb():
    """The distro-name preference is MySQL's to state, not the helper's."""
    with patch.object(mysql, "control_service") as controlled:
        mysql._start_mysql_service()

    assert controlled.call_args[0] == ("start", "mysql", "mariadb")


def _result(returncode: int = 0, stdout: str = ""):
    return type("R", (), {"returncode": returncode, "stdout": stdout, "stderr": ""})()


def test_redis_restart_goes_through_the_helper():
    """`systemctl restart redis-server` with check=False was a no-op here."""
    with (
        patch.object(redis, "control_service") as controlled,
        patch.object(redis, "_write_redis_config", return_value=None),
        patch.object(redis, "has_systemd", return_value=True),
        patch.object(redis, "run_cmd", return_value=_result(stdout="PONG")),
    ):
        redis.configure_redis()

    assert ("restart", "redis-server", "redis") in [
        c.args for c in controlled.call_args_list
    ]


def test_redis_without_systemd_is_shut_down_by_asking_it():
    """
    An init script's stop finds Redis by its pidfile and reports success
    without one, so a "restart" left the old Redis serving the old config.
    """
    calls: list = []
    running = iter([0, 1])  # pgrep: still there once, then gone

    def run(cmd, *_a, **_kw):
        calls.append(cmd)
        if cmd[0] == "pgrep":
            return _result(next(running))
        return _result(stdout="PONG")

    with (
        patch.object(redis, "control_service", side_effect=lambda *a: calls.append(a)),
        patch.object(redis, "_write_redis_config", return_value=None),
        patch.object(redis, "has_systemd", return_value=False),
        patch.object(redis, "run_cmd", side_effect=run),
        patch.object(redis.time, "sleep"),
    ):
        redis.configure_redis()

    shutdown = calls.index(["redis-cli", "SHUTDOWN"])
    start = calls.index(("start", "redis-server", "redis"))
    assert shutdown < start
    assert ("restart", "redis-server", "redis") not in calls


def test_a_redis_that_survives_its_shutdown_stops_the_install():
    def run(cmd, *_a, **_kw):
        return _result(0, "NOAUTH Authentication required.")

    with (
        patch.object(redis, "control_service") as controlled,
        patch.object(redis, "_write_redis_config", return_value=None),
        patch.object(redis, "has_systemd", return_value=False),
        patch.object(redis, "run_cmd", side_effect=run),
        patch.object(redis.time, "sleep"),
        pytest.raises(InstallStepError, match="NOAUTH"),
    ):
        redis.configure_redis()

    controlled.assert_not_called()


def test_redis_that_cannot_restart_stops_the_install():
    """A failure here is why an app's redis addon dies later, so stop now."""
    failure = CommandError(
        cmd=["systemctl", "restart"], returncode=1, stdout="", stderr="x"
    )
    with (
        patch.object(redis, "control_service", side_effect=failure),
        patch.object(redis, "_write_redis_config", return_value=None),
        patch.object(redis, "has_systemd", return_value=False),
        pytest.raises(CommandError),
    ):
        redis.configure_redis()


def test_redis_is_given_time_to_listen_after_a_restart():
    """
    An init script returns at fork: one PING straight after the restart
    failed the install intermittently.
    """
    replies = iter(["", "", "PONG"])

    def ping(*_a, **_kw):
        return type("R", (), {"returncode": 0, "stdout": next(replies), "stderr": ""})()

    with (
        patch.object(redis, "control_service"),
        patch.object(redis, "_write_redis_config", return_value=None),
        patch.object(redis, "has_systemd", return_value=False),
        patch.object(redis, "_shutdown_redis"),
        patch.object(redis, "run_cmd", side_effect=ping),
        patch.object(redis.time, "sleep"),
    ):
        redis.configure_redis()
