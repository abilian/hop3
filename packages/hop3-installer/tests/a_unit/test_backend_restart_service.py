# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""The upgrade restart must match the target's process manager.

Real servers run hop3-server under systemd; the Docker deploy target runs it
under supervisor (its PID 1 — no systemd). A hardcoded ``systemctl restart``
silently no-ops on Docker, so an upgrade would keep serving the OLD code while
reporting success. The backend picks the right command.
"""

from __future__ import annotations

from types import SimpleNamespace

from hop3_installer.deployer.backends.base import DeployBackend
from hop3_installer.deployer.backends.docker import DockerDeployBackend
from hop3_installer.deployer.backends.ssh import SSHDeployBackend
from hop3_installer.deployer.config import DeployConfig


class _StubBackend(DeployBackend):
    """A concrete backend that records the command restart_service runs."""

    def __init__(self):
        super().__init__(DeployConfig())
        self.calls: list[tuple[str, bool]] = []

    def run(self, command, *, check=True, stdin=None):
        self.calls.append((command, check))
        return SimpleNamespace(success=True, returncode=0, stdout="", stderr="")

    def setup(self) -> bool:
        return True

    def teardown(self) -> None:
        pass

    def upload_file(self, local_path, remote_path) -> bool:
        return True

    def upload_dir(self, local_path, remote_path) -> bool:
        return True

    def clean(self) -> None:
        pass

    def get_server_url(self) -> str:
        return "http://localhost:8000"


def test_default_backend_uses_systemctl():
    assert (
        _StubBackend().service_restart_command("hop3-server")
        == "systemctl restart hop3-server"
    )


def test_ssh_backend_inherits_systemd():
    # Real servers: systemd manages the service.
    ssh = SSHDeployBackend(DeployConfig())
    assert ssh.service_restart_command("hop3-server") == "systemctl restart hop3-server"


def test_docker_backend_uses_supervisorctl():
    # Supervisor is PID 1 in the container; systemctl would silently no-op.
    docker = DockerDeployBackend(DeployConfig())
    assert (
        docker.service_restart_command("hop3-server")
        == "supervisorctl restart hop3-server"
    )


def test_restart_service_runs_the_target_command_best_effort():
    backend = _StubBackend()
    backend.restart_service("hop3-server")
    # Best-effort (check=False): the deployer verifies health afterwards, so a
    # restart that leaves a crashing process is caught there, not masked here.
    assert backend.calls == [("systemctl restart hop3-server", False)]
