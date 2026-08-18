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
from hop3_installer.common import control_service
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
        assert control_service("start", "mysql", "mariadb") is True

    assert commands == [["systemctl", "start", "mysql"]]


def test_a_container_uses_the_init_script(commands):
    """The branch that did not exist. `systemctl` is not even attempted."""
    with (
        patch.object(common, "has_systemd", return_value=False),
        patch.object(Path, "is_file", return_value=True),
    ):
        assert control_service("start", "mysql", "mariadb") is True

    assert commands == [["/etc/init.d/mysql", "start"]]
    assert not any("systemctl" in c for c in commands)


def test_the_second_name_is_tried_when_the_first_has_no_script(commands):
    with (
        patch.object(common, "has_systemd", return_value=False),
        patch.object(Path, "is_file", lambda self: self.name == "mariadb"),
    ):
        assert control_service("start", "mysql", "mariadb") is True

    assert commands == [["/etc/init.d/mariadb", "start"]]


def test_no_init_script_at_all_is_a_failure(commands):
    """Not a silent success: the caller aborts the install on False."""
    with (
        patch.object(common, "has_systemd", return_value=False),
        patch.object(Path, "is_file", return_value=False),
    ):
        assert control_service("start", "mysql") is False

    assert commands == []


def test_mysql_prefers_mysql_then_mariadb():
    """The distro-name preference is MySQL's to state, not the helper's."""
    with patch.object(mysql, "control_service", return_value=True) as controlled:
        mysql._start_mysql_service()

    assert controlled.call_args[0] == ("start", "mysql", "mariadb")


def test_redis_restart_goes_through_the_helper():
    """`systemctl restart redis-server` with check=False was a no-op here."""
    with (
        patch.object(redis, "control_service", return_value=True) as controlled,
        patch.object(redis, "_configure_redis_bind"),
        patch.object(redis, "has_systemd", return_value=False),
        patch.object(
            redis,
            "run_cmd",
            return_value=type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
        ),
    ):
        redis.configure_redis()

    assert ("restart", "redis-server") in [c.args for c in controlled.call_args_list]


def test_redis_says_so_when_it_cannot_restart(capsys):
    """A failure here is why an app's redis addon dies later, so name it now."""
    with (
        patch.object(redis, "control_service", return_value=False),
        patch.object(redis, "_configure_redis_bind"),
        patch.object(redis, "has_systemd", return_value=False),
        patch.object(
            redis,
            "run_cmd",
            return_value=type("R", (), {"returncode": 1, "stdout": "", "stderr": ""})(),
        ),
    ):
        redis.configure_redis()

    assert "Redis could not be restarted" in capsys.readouterr().out
