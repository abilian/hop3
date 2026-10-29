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

The tests pass a recording runner (and the init-script directory) through the
helpers' own parameters, and assert the commands it recorded.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable

import pytest
from hop3_installer.common import CommandError, InstallStepError, control_service
from hop3_installer.server_installer import mysql, redis

Reply = Callable[[list[str]], tuple[int, str]]


class Recorder:
    """A runner that records each command and answers through ``reply``."""

    def __init__(self, reply: Reply | None = None) -> None:
        self.commands: list[list[str]] = []
        self.envs: list[dict[str, str] | None] = []
        self._reply = reply or (lambda _cmd: (0, ""))

    def __call__(self, cmd, *, env=None, **_kwargs) -> subprocess.CompletedProcess:
        self.commands.append(list(cmd))
        self.envs.append(env)
        returncode, stdout = self._reply(list(cmd))
        stderr = "" if returncode == 0 else "unit failed"
        return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)


def _init_dir(tmp_path, *scripts: str):
    for name in scripts:
        (tmp_path / name).write_text("#!/bin/sh\n")
    return tmp_path


def test_systemd_hosts_use_systemctl():
    run = Recorder()
    control_service("start", "mysql", "mariadb", run=run, systemd=True)

    assert run.commands == [["systemctl", "start", "mysql"]]


def test_a_container_uses_the_init_script(tmp_path):
    """The branch that did not exist. `systemctl` is not even attempted."""
    run = Recorder()
    init_dir = _init_dir(tmp_path, "mysql", "mariadb")
    control_service(
        "start", "mysql", "mariadb", run=run, systemd=False, init_dir=init_dir
    )

    assert run.commands == [[str(init_dir / "mysql"), "start"]]


def test_the_second_name_is_tried_when_the_first_has_no_script(tmp_path):
    run = Recorder()
    init_dir = _init_dir(tmp_path, "mariadb")
    control_service(
        "start", "mysql", "mariadb", run=run, systemd=False, init_dir=init_dir
    )

    assert run.commands == [[str(init_dir / "mariadb"), "start"]]


def test_no_init_script_at_all_is_a_failure(tmp_path):
    """Not a silent success: the install stops, naming the services tried."""
    run = Recorder()
    with pytest.raises(InstallStepError, match="no init script for mysql"):
        control_service("start", "mysql", run=run, systemd=False, init_dir=tmp_path)

    assert run.commands == []


def test_a_failed_systemctl_carries_its_output():
    """
    It returned False, and the caller aborted with "Redis did not restart"
    and nothing else: no stderr, no journal.
    """
    run = Recorder(
        lambda cmd: (0, "journal tail") if cmd[0] == "journalctl" else (1, "")
    )
    with pytest.raises(CommandError) as raised:
        control_service("restart", "redis-server", "redis", run=run, systemd=True)

    assert "systemctl restart redis-server: unit failed" in raised.value.stderr
    assert raised.value.stdout == "journal tail"


def test_mysql_prefers_mysql_then_mariadb():
    """The distro-name preference is MySQL's to state, not the helper's."""
    assert mysql._MYSQL_SERVICE_NAMES == ("mysql", "mariadb")


def test_mysql_admin_candidates_never_use_sudo(monkeypatch):
    """The installer runs as root: socket auth needs no sudo, and Hop3 uses none."""
    tried: list[list[str]] = []

    def run(cmd, **_kwargs):
        tried.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 1, "", "denied")

    monkeypatch.setattr(mysql, "run_cmd", run)
    monkeypatch.setattr(mysql, "_get_debian_mysql_credentials", lambda: None)
    assert mysql._find_mysql_admin_connection() is None
    assert tried, "no candidate was tried"
    assert not any("sudo" in cmd for cmd in tried)


# --- Redis --------------------------------------------------------------------


@pytest.fixture(autouse=True)
def redis_host(tmp_path, monkeypatch):
    """The test's own password file and config; no waiting between polls."""
    monkeypatch.setattr(redis, "REDIS_PASS_FILE", tmp_path / "redis-pass")
    monkeypatch.setattr(redis, "_write_redis_config", lambda: None)
    monkeypatch.setattr(redis, "_PING_DELAY", 0)


def _pong(cmd: list[str]) -> tuple[int, str]:
    return (0, "PONG") if cmd[:2] == ["redis-cli", "PING"] else (0, "")


def test_redis_restart_goes_through_the_helper():
    """`systemctl restart redis-server` with check=False was a no-op here."""
    run = Recorder(_pong)
    redis.configure_redis(run=run, systemd=True)

    assert ["systemctl", "enable", "redis-server"] in run.commands
    assert ["systemctl", "restart", "redis-server"] in run.commands


def test_redis_without_systemd_is_shut_down_by_asking_it(tmp_path, monkeypatch):
    """
    An init script's stop finds Redis by its pidfile and reports success
    without one, so a "restart" left the old Redis serving the old config.
    """
    monkeypatch.setattr(redis, "control_service", _control_in(tmp_path))
    running = iter([0, 1])  # pgrep: still there once, then gone

    def reply(cmd):
        return (next(running), "") if cmd[0] == "pgrep" else _pong(cmd)

    run = Recorder(reply)
    redis.configure_redis(run=run, systemd=False)

    shutdown = run.commands.index(["redis-cli", "SHUTDOWN"])
    start = run.commands.index([str(tmp_path / "redis-server"), "start"])
    assert shutdown < start
    assert not any(cmd[0] == "systemctl" for cmd in run.commands)


def _control_in(init_dir):
    """`control_service` reading init scripts from the test's directory."""
    _init_dir(init_dir, "redis-server")

    def control(action, *names, **kwargs):
        control_service(action, *names, **kwargs, init_dir=init_dir)

    return control


def test_a_redis_that_survives_its_shutdown_stops_the_install(tmp_path, monkeypatch):
    monkeypatch.setattr(redis, "control_service", _control_in(tmp_path))
    run = Recorder(lambda _cmd: (0, "NOAUTH Authentication required."))

    with pytest.raises(InstallStepError, match="NOAUTH"):
        redis.configure_redis(run=run, systemd=False)

    assert not any(cmd[-1] == "start" for cmd in run.commands)


def test_redis_that_cannot_restart_stops_the_install():
    """A failure here is why an app's redis addon dies later, so stop now."""
    run = Recorder(lambda cmd: (1, "") if cmd[0] == "systemctl" else (0, ""))

    with pytest.raises(CommandError):
        redis.configure_redis(run=run, systemd=True)


def test_redis_is_given_time_to_listen_after_a_restart():
    """
    An init script returns at fork: one PING straight after the restart
    failed the install intermittently.
    """
    replies = iter(["", "", "PONG"])

    def reply(cmd):
        return (0, next(replies)) if cmd[:2] == ["redis-cli", "PING"] else (0, "")

    run = Recorder(reply)
    redis.configure_redis(run=run, systemd=True)

    assert run.commands.count(["redis-cli", "PING"]) == 3


def test_redis_ping_authenticates_when_a_password_is_set(monkeypatch):
    """Without it, a Redis with requirepass answers NOAUTH and fails the check."""
    monkeypatch.setattr(redis, "_write_redis_config", lambda: "s3cret")
    run = Recorder(_pong)
    redis.configure_redis(run=run, systemd=True)

    ping = run.commands.index(["redis-cli", "PING"])
    assert run.envs[ping] == {"REDISCLI_AUTH": "s3cret"}
