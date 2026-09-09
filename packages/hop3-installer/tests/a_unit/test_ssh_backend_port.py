# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
A non-default SSH port reaches each tool in that tool's own spelling.

`-p PORT` is ssh's flag. scp reads `-p` as "preserve times" and would take the
port number for a file to copy, so the backend once broke every upload to a
server on a non-standard port while its ssh commands worked.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hop3_installer.deployer.backends.ssh import SSHDeployBackend
from hop3_installer.deployer.config import DeployConfig


def _argv_of(backend, call):
    seen: list[list[str]] = []

    def record(argv, **_kwargs):
        seen.append(list(argv))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    with patch(
        "hop3_installer.deployer.backends.ssh.subprocess.run", side_effect=record
    ):
        call(backend)
    return seen[0]


def test_ssh_gets_dash_p_and_scp_gets_dash_capital_p():
    backend = SSHDeployBackend(DeployConfig(host="h.test", ssh_port=2222))
    ssh = _argv_of(backend, lambda b: b.run("true", check=False))
    scp = _argv_of(backend, lambda b: b.upload_file(Path("/tmp/f"), "/tmp/f"))
    assert ssh[:1] == ["ssh"]
    assert "-p" in ssh
    assert ssh[ssh.index("-p") + 1] == "2222"
    assert scp[:1] == ["scp"]
    assert "-P" in scp
    assert "-p" not in scp


def test_rsync_carries_the_port_in_its_ssh_transport():
    backend = SSHDeployBackend(DeployConfig(host="h.test", ssh_port=2222))
    up = _argv_of(backend, lambda b: b.upload_dir(Path("/tmp/d"), "/tmp/d"))
    down = _argv_of(backend, lambda b: b.download_dir("/tmp/d", Path("/tmp/local")))
    for argv in (up, down):
        assert argv[0] == "rsync"
        assert "-p 2222" in argv[argv.index("-e") + 1]


def test_default_port_adds_nothing():
    backend = SSHDeployBackend(DeployConfig(host="h.test"))
    ssh = _argv_of(backend, lambda b: b.run("true", check=False))
    assert "-p" not in ssh
    assert "-P" not in ssh


def test_ssh_options_reach_ssh_scp_and_rsync():
    backend = SSHDeployBackend(
        DeployConfig(host="h.test", ssh_options=["UserKnownHostsFile=/tmp/kh"])
    )
    ssh = _argv_of(backend, lambda b: b.run("true", check=False))
    scp = _argv_of(backend, lambda b: b.upload_file(Path("/tmp/f"), "/tmp/f"))
    down = _argv_of(backend, lambda b: b.download_dir("/tmp/d", Path("/tmp/local")))
    assert (
        ssh[ssh.index("-o", ssh.index("ConnectTimeout=10")) + 1]
        == "UserKnownHostsFile=/tmp/kh"
        or "UserKnownHostsFile=/tmp/kh" in ssh
    )
    assert "UserKnownHostsFile=/tmp/kh" in scp
    assert "UserKnownHostsFile=/tmp/kh" in down[down.index("-e") + 1]
