# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
An exec's output survives the headers being read ahead of it over ssh://.

The gate and proxy e2e tests failed at random against a remote daemon with
"curl exited 0, stdout ''": the output had arrived in the same read as the
response headers and stayed in paramiko's buffer, where docker-py never looks.
"""

from __future__ import annotations

import socket
import struct
from types import SimpleNamespace

import docker
from hop3_testing.docker_client import DockerClient, _APIClient

STDOUT = 1
OUTPUT = b"HTTP/1.1 200 OK\r\n\r\nbody"


def _frame(stream: int, data: bytes) -> bytes:
    return struct.pack(">BxxxL", stream, len(data)) + data


class _ChannelFile:
    """paramiko's BufferedFile, reduced: what the headers' read left, then the channel."""

    def __init__(self, channel: socket.socket, read_ahead: bytes) -> None:
        self.channel = channel
        self._rbuffer = read_ahead  # docker-py's path skips this buffer

    def read(self, size: int) -> bytes:
        data, self._rbuffer = self._rbuffer[:size], self._rbuffer[size:]
        while len(data) < size and (more := self.channel.recv(size - len(data))):
            data += more
        return data


def _output(client_class: type, monkeypatch) -> tuple[bytes | None, bytes | None]:
    """
    Read an exec's output through docker-py's own path (``exec_run`` uses it).

    The channel is the drained one that read leaves: nothing more to come, then
    EOF (a socket whose peer has closed, so docker-py's poll returns too).
    """
    monkeypatch.setattr(docker.APIClient, "_raise_for_status", lambda self, r: None)
    channel, peer = socket.socketpair()
    peer.close()
    channel_file = _ChannelFile(channel, read_ahead=_frame(STDOUT, OUTPUT))
    response = SimpleNamespace(
        raw=SimpleNamespace(_fp=SimpleNamespace(fp=channel_file)), close=lambda: None
    )
    api = client_class.__new__(client_class)
    api.base_url = "http+docker://ssh"
    try:
        return api._read_from_socket(response, stream=False, tty=False, demux=True)
    finally:
        channel.close()


def test_docker_py_alone_loses_output_read_ahead(monkeypatch) -> None:
    """The failure, reproduced: the output is in the buffer, docker-py reads past it."""
    assert _output(docker.APIClient, monkeypatch) == (None, None)


def test_the_output_read_ahead_is_returned(monkeypatch) -> None:
    assert _output(_APIClient, monkeypatch) == (OUTPUT, None)


def test_from_env_builds_the_fixed_client(monkeypatch) -> None:
    monkeypatch.setenv("DOCKER_HOST", "unix:///nonexistent.sock")
    client = DockerClient.from_env(version="1.44")  # a version: no daemon asked
    assert isinstance(client.api, _APIClient)
