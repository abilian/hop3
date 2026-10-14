# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
One Docker daemon per run: the CLI's choice, pinned for docker-py too.

With the current context on a remote machine, the deployer started its
container there through the `docker` CLI while the harness looked for it on the
local socket through docker-py, which ignores contexts.
"""

from __future__ import annotations

import os
import stat
from typing import TYPE_CHECKING

import pytest
from hop3_installer.deployer.docker_endpoint import DockerEndpoint, pin_docker_endpoint

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    ("url", "host"),
    [
        ("unix:///var/run/docker.sock", "localhost"),
        ("ssh://fermigier@fedora.local", "fedora.local"),
        ("ssh://builder@10.0.0.7:2222", "10.0.0.7"),
        ("tcp://docker.example.com:2376", "docker.example.com"),
    ],
)
def test_published_ports_answer_on_the_daemons_machine(url, host):
    assert DockerEndpoint(url).published_host == host


def test_an_endpoint_without_a_host_is_refused():
    with pytest.raises(RuntimeError, match="names no host"):
        _ = DockerEndpoint("tcp://").published_host


def _fake_docker(tmp_path: Path, monkeypatch, *, output: str, rc: int = 0) -> None:
    """A `docker` on PATH that prints ``output`` for `context inspect`."""
    script = tmp_path / "docker"
    script.write_text(f"#!/bin/sh\necho '{output}'\nexit {rc}\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")


def test_the_cli_context_is_pinned_for_everything_after(tmp_path, monkeypatch):
    _fake_docker(tmp_path, monkeypatch, output="ssh://fermigier@fedora.local")
    monkeypatch.delenv("DOCKER_HOST", raising=False)

    endpoint = pin_docker_endpoint()

    assert endpoint.url == "ssh://fermigier@fedora.local"
    assert os.environ["DOCKER_HOST"] == "ssh://fermigier@fedora.local"


def test_an_explicit_docker_host_wins(tmp_path, monkeypatch):
    _fake_docker(tmp_path, monkeypatch, output="ssh://elsewhere")
    monkeypatch.setenv("DOCKER_HOST", "unix:///var/run/docker.sock")

    assert pin_docker_endpoint().url == "unix:///var/run/docker.sock"


def test_an_unknown_endpoint_fails_loudly(tmp_path, monkeypatch):
    _fake_docker(tmp_path, monkeypatch, output="context not found", rc=1)
    monkeypatch.delenv("DOCKER_HOST", raising=False)

    with pytest.raises(RuntimeError, match="docker context inspect"):
        pin_docker_endpoint()
