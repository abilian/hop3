# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Failures the installer and deployer used to swallow, and now surface.

Each test names what was lost: a timeout reported as success, a secret rotated
because its file was unreadable, an uninstall that printed success over failed
steps, a private key left with the wrong mode, a transfer failure with no
reason, a nix-daemon that never re-read its config, a missing Python replaced
by whatever `python3` was, a server installed without its `hop3` client.
"""

from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace

import pytest
from hop3_installer.common import CommandError, InstallStepError, run_cmd
from hop3_installer.deployer.backends import ssh as ssh_mod
from hop3_installer.deployer.backends.docker import DockerDeployBackend
from hop3_installer.deployer.backends.ssh import SSHDeployBackend
from hop3_installer.deployer.config import DeployConfig
from hop3_installer.deployer.deploy import Deployer
from hop3_installer.server_installer import (
    nix,
    python as python_step,
    rootd,
    s3,
    services,
    verify,
)
from hop3_installer.server_installer.config import ServerInstallerConfig


def _ok(stdout: str = ""):
    return SimpleNamespace(success=True, returncode=0, stdout=stdout, stderr="")


def _fail(stderr: str):
    return SimpleNamespace(success=False, returncode=1, stdout="", stderr=stderr)


# --- run_cmd ------------------------------------------------------------------


def test_a_timed_out_command_raises_under_check():
    with pytest.raises(CommandError) as raised:
        run_cmd([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.2)
    assert raised.value.returncode == -1
    assert "timed out after 0.2s" in raised.value.stderr


def test_a_timed_out_command_reads_as_failure_without_check():
    result = run_cmd(
        [sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.2, check=False
    )
    assert result.returncode == -1


# --- secrets and operator lines survive an unreadable file --------------------


@pytest.mark.parametrize(
    ("module", "attr", "read"),
    [
        (services, "SECRET_KEY_FILE", services._read_secret_key_file),
        (s3, "GARAGE_CONFIG_FILE", lambda: s3._existing_secret("admin_token")),
    ],
)
def test_an_unreadable_secret_aborts_instead_of_regenerating(
    tmp_path, monkeypatch, module, attr, read
):
    # A directory reads as IsADirectoryError: an OSError that is not absence.
    monkeypatch.setattr(module, attr, tmp_path)
    with pytest.raises(OSError, match=str(tmp_path)):
        read()


@pytest.mark.parametrize(
    "read",
    [
        lambda: verify.read_existing_server_config_value("MYSQL_SUPERUSER_PASSWORD"),
        verify._preserved_operator_lines,
    ],
)
def test_an_unreadable_server_config_aborts(
    tmp_path, monkeypatch, read, hop3_shell_is_local
):
    # A directory: `cat` fails, which is not absence.
    (tmp_path / "hop3-server.toml").mkdir()
    monkeypatch.setattr(verify, "HOME_DIR", tmp_path)
    with pytest.raises(CommandError):
        read()


def test_a_missing_file_still_means_first_install(
    tmp_path, monkeypatch, hop3_shell_is_local
):
    monkeypatch.setattr(services, "SECRET_KEY_FILE", tmp_path / "absent")
    monkeypatch.setattr(s3, "GARAGE_CONFIG_FILE", tmp_path / "absent")
    monkeypatch.setattr(verify, "HOME_DIR", tmp_path)
    assert services._read_secret_key_file() is None
    assert s3._existing_secret("admin_token") is None
    assert verify.read_existing_server_config_value("X") is None
    assert verify._preserved_operator_lines() == []


# --- rootd uninstall ----------------------------------------------------------


def test_rootd_uninstall_reports_failed_steps_not_success(
    tmp_path, monkeypatch, capsys
):
    for name in ("SERVICE_PATH", "SOCKET_PATH", "LOGROTATE_PATH", "STATE_FILE"):
        path = tmp_path / name
        path.write_text("")
        monkeypatch.setattr(rootd, name, path)
    monkeypatch.setattr(rootd, "BIND_ALLOWLIST_FILE", tmp_path / "allow")
    monkeypatch.setattr(rootd, "has_systemd", lambda: True)

    def run(cmd, **_kw):
        failed = cmd[:2] == ["systemctl", "disable"]
        return subprocess.CompletedProcess(cmd, 1 if failed else 0, "", "boom")

    monkeypatch.setattr(rootd, "run_cmd", run)
    with pytest.raises(InstallStepError, match=r"hop3-rootd\.service.*boom"):
        rootd.uninstall_rootd()
    assert "uninstalled" not in capsys.readouterr().out


# --- deployer: certificate permissions, Python ---------------------------------


class _Backend:
    """Fails every command containing one of ``failing``; records the rest."""

    def __init__(self, *failing: str) -> None:
        self.failing = failing
        self.commands: list[str] = []

    def run(self, cmd, check=False, stdin=None):
        self.commands.append(cmd)
        if any(f in cmd for f in self.failing):
            return _fail(f"failed: {cmd}")
        return _ok()


def _deployer(backend, config: DeployConfig | None = None) -> Deployer:
    return Deployer(config or DeployConfig(), backend=backend)  # type: ignore[arg-type]


def test_a_private_key_left_unprotected_fails_the_deploy(capsys):
    backend = _Backend("chmod 600")
    assert _deployer(backend)._generate_self_signed_cert("x.example", "/c") is False
    assert "chmod 600" in capsys.readouterr().out
    assert not any("cat >" in c for c in backend.commands), "nginx not reconfigured"


def test_no_usable_python_aborts_with_both_dnf_outputs(capsys):
    backend = _Backend("python3 -c", "command -v python3.1", "dnf install")
    assert _deployer(backend)._ensure_python310_plus() is None
    out = capsys.readouterr().out
    assert "python3.12-devel" in out
    assert "python3.11-devel" in out


def test_no_dnf_and_no_python_is_a_failure_not_python3(capsys):
    backend = _Backend("python3 -c", "command -v")
    assert _deployer(backend)._ensure_python310_plus() is None
    assert "No Python 3.10+" in capsys.readouterr().out


def test_a_missing_cli_package_stops_the_deploy_before_the_upload(tmp_path, capsys):
    (tmp_path / "packages").mkdir()
    deployer = _deployer(_Backend(), DeployConfig(project_root=tmp_path))
    assert deployer._upload_cli_package() is False
    assert "hop3-cli package not found" in capsys.readouterr().out


def test_a_missing_cli_source_stops_the_install(tmp_path, monkeypatch):
    (tmp_path / "hop3-server").mkdir()
    ran: list[object] = []
    monkeypatch.setattr(python_step, "run_as_hop3", lambda *a, **k: ran.append(a))
    config = ServerInstallerConfig(local_path=str(tmp_path / "hop3-server"))

    with pytest.raises(InstallStepError, match="hop3-cli source not found"):
        python_step.install_cli_package(config)
    assert ran == []


def test_a_pre_release_install_takes_the_pre_release_client(monkeypatch):
    installs: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        python_step, "_pip_install_own", lambda *a, **_k: installs.append(a)
    )
    python_step.install_cli_package(ServerInstallerConfig(pre_release=True))
    assert installs == [("/home/hop3/venv/bin/pip", "hop3-cli", "--pre")]


# --- backends: transfers and clean ---------------------------------------------


def test_a_failed_scp_prints_its_reason(monkeypatch, capsys, tmp_path):
    def run(argv, **_kw):
        return subprocess.CompletedProcess(argv, 1, "", "Permission denied")

    monkeypatch.setattr(ssh_mod.subprocess, "run", run)
    backend = SSHDeployBackend(DeployConfig(host="example.com"))
    assert backend.upload_file(tmp_path / "f", "/tmp/f") is False
    assert "Permission denied" in capsys.readouterr().out


def test_an_upload_whose_chmod_fails_is_a_failed_upload(monkeypatch, tmp_path):
    monkeypatch.setattr(
        ssh_mod.subprocess,
        "run",
        lambda argv, **_kw: subprocess.CompletedProcess(argv, 0, "", ""),
    )
    backend = SSHDeployBackend(DeployConfig(host="example.com"))
    monkeypatch.setattr(backend, "run", lambda *_a, **_kw: _fail("read-only"))
    assert backend.upload_dir(tmp_path, "/tmp/pkg") is False


def test_ssh_clean_raises_when_a_service_will_not_stop(monkeypatch):
    backend = SSHDeployBackend(DeployConfig(host="example.com"))

    def run(cmd, *, check=True, stdin=None):
        result = _fail("stop failed") if "systemctl stop" in cmd else _ok()
        backend._raise_if_failed(result, cmd, check=check)
        return result

    monkeypatch.setattr(backend, "run", run)
    with pytest.raises(RuntimeError, match="systemctl stop hop3-server"):
        backend.clean()


def test_docker_clean_stops_through_supervisor_not_systemctl(monkeypatch):
    backend = DockerDeployBackend.__new__(DockerDeployBackend)
    commands: list[str] = []
    monkeypatch.setattr(
        backend, "run", lambda cmd, **_kw: commands.append(cmd) or _ok()
    )
    backend.clean()
    assert "supervisorctl stop hop3-server" in commands[0]
    assert not any("systemctl" in c.replace("supervisorctl", "") for c in commands)


# --- server installer: nix daemon, hints --------------------------------------


def _files_absent(script, **_kw):
    """hop3's shell, on a home where no file exists yet."""
    return subprocess.CompletedProcess(script, 3 if "test -e" in script else 0, "", "")


def test_a_failed_nix_daemon_restart_stops_the_install(tmp_path):
    def run(cmd, **_kw):
        return subprocess.CompletedProcess(cmd, 1, "", "no unit")

    with pytest.raises(CommandError, match="nix-daemon"):
        nix._configure_hop3_nix_access(
            daemon_mode=True,
            home=tmp_path,
            etc_conf=tmp_path / "nix.conf",
            run=run,
            as_hop3_shell=_files_absent,
            systemd=True,
        )


@pytest.mark.parametrize("systemd", [True, False])
def test_service_hints_match_the_process_manager(monkeypatch, systemd):
    monkeypatch.setattr(verify, "has_systemd", lambda: systemd)
    hints = "\n".join(verify._service_hints())
    assert "sudo" not in hints
    assert ("systemctl" in hints) is systemd
    assert ("supervisorctl" in hints) is not systemd
