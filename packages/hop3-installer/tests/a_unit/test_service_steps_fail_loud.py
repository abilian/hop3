# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The service setup steps abort on failure; verification fails what is broken.

They used to catch each step's failure and print a warning, error output cut
to 100 characters, then report "Installation complete!": a failed nginx, SSL
or config write gave a server that did not work and an install that said it
did. On the Docker target, `systemctl` failed on every install ("System has not
been booted with systemd") and was caught the same way, which also hid the
failure on a real systemd host. See notes/installer-fail-loud-audit.md.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from hop3_installer.common import CommandError, InstallStepError
from hop3_installer.server_installer import (
    deps_common,
    installer,
    redis,
    services,
    verify,
)


def _ok(stdout: str = "") -> SimpleNamespace:
    return SimpleNamespace(returncode=0, stdout=stdout, stderr="")


def test_without_systemd_no_unit_is_installed_and_no_systemctl_runs(capsys):
    calls: list[list[str]] = []

    def fake_run(cmd, **_kw):
        calls.append(cmd)
        return _ok()

    with (
        patch.object(services, "setup_environment_file", return_value="k" * 64),
        patch.object(services, "has_systemd", return_value=False),
        patch.object(services, "run_cmd", side_effect=fake_run),
    ):
        assert services.setup_systemd() == "k" * 64

    assert calls == []
    assert "process manager runs the services" in capsys.readouterr().out


def test_a_unit_that_will_not_restart_aborts(tmp_path):
    def fake_run(cmd, **_kw):
        if cmd[:2] == ["systemctl", "restart"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="failed")
        return _ok("journal tail")

    with (
        patch.object(services, "setup_environment_file", return_value="k"),
        patch.object(services, "has_systemd", return_value=True),
        patch.object(services, "run_cmd", side_effect=fake_run),
        patch.object(services, "Path", side_effect=lambda p: tmp_path / p.lstrip("/")),
    ):
        (tmp_path / "etc/systemd/system").mkdir(parents=True)
        with pytest.raises(CommandError) as raised:
            services.setup_systemd()

    assert raised.value.cmd == ["systemctl", "restart", "hop3-server"]
    assert "journal tail" in raised.value.stdout


def test_a_failed_step_ends_the_install_with_its_output(monkeypatch, capsys):
    def nginx_fails(*_a, **_kw):
        raise CommandError(
            cmd=["nginx", "-t"], returncode=1, stderr="unknown directive", stdout=""
        )

    monkeypatch.setattr(installer, "_configure_server", nginx_fails)
    monkeypatch.setattr(installer, "_run_critical_steps", lambda *_a: True)
    monkeypatch.setattr(installer, "check_python_version", lambda: True)
    monkeypatch.setattr(installer.os, "geteuid", lambda: 0)
    monkeypatch.setattr(installer.sys, "argv", ["install-server.py"])
    verified: list[bool] = []
    monkeypatch.setattr(
        installer, "verify_installation", lambda _c: verified.append(True) or True
    )

    assert installer.main() == 1
    assert verified == [], "nothing is verified, or reported, after a failed step"
    err = capsys.readouterr()
    assert "unknown directive" in err.out + err.err


@pytest.mark.parametrize("missing", ["service", "toml"])
def test_verification_fails_what_is_broken(monkeypatch, tmp_path, missing):
    monkeypatch.setattr(verify, "VENV_DIR", tmp_path)
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "hop3-server").touch()
    monkeypatch.setattr(verify, "HOME_DIR", tmp_path)
    if missing != "toml":
        (tmp_path / "hop3-server.toml").write_text("")
    cert, key = tmp_path / "c.pem", tmp_path / "k.pem"
    cert.touch()
    key.touch()
    monkeypatch.setattr(verify, "SYSTEM_SSL_CERT", cert)
    monkeypatch.setattr(verify, "SYSTEM_SSL_KEY", key)
    monkeypatch.setattr(verify, "process_manager_pending", lambda: False)
    monkeypatch.setattr(verify, "has_systemd", lambda: True)
    active = "inactive" if missing == "service" else "active"
    monkeypatch.setattr(verify, "run_cmd", lambda *_a, **_kw: _ok(active))

    assert verify.verify_installation(SimpleNamespace()) is False


def test_docker_requested_without_systemd_aborts_with_the_reason():
    """It printed "Failed to start Docker daemon" and the install carried on."""
    with (
        patch.object(deps_common, "has_systemd", return_value=False),
        pytest.raises(InstallStepError, match="no systemd to run dockerd"),
    ):
        deps_common._start_docker_daemon()


def test_redis_replica_setting_is_removed_from_the_config(tmp_path, monkeypatch):
    """
    The runtime CONFIG SET / REPLICAOF this replaced ran before the restart,
    which discarded them; only the config file survives a restart.
    """
    conf = tmp_path / "redis.conf"
    conf.write_text("port 6379\nreplicaof 10.0.0.1 6379\nbind 127.0.0.1\n")
    monkeypatch.setattr(redis, "REDIS_CONF_PATHS", [conf])
    monkeypatch.setattr(redis, "get_docker_bridge_ip", lambda: None)

    assert redis._write_redis_config() is None
    assert "replicaof" not in conf.read_text()
    assert "port 6379" in conf.read_text()


def test_redis_ping_authenticates_when_a_password_is_set(monkeypatch):
    """Without it, a Redis with requirepass answers NOAUTH and fails the check."""
    seen: dict = {}

    def run(cmd, env=None, **_kw):
        seen["env"] = env
        return SimpleNamespace(returncode=0, stdout="PONG", stderr="")

    monkeypatch.setattr(redis, "_write_redis_config", lambda: "s3cret")
    monkeypatch.setattr(redis, "has_systemd", lambda: False)
    monkeypatch.setattr(redis, "control_service", lambda *_a: True)
    monkeypatch.setattr(redis, "run_cmd", run)

    redis.configure_redis()
    assert seen["env"] == {"REDISCLI_AUTH": "s3cret"}
