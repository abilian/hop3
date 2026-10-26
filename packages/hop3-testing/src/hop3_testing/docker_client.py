# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
A docker-py client whose ``exec_run`` keeps its output over an ``ssh://`` daemon.

docker-py reads an exec's output from the bare paramiko channel under the
response (``response.raw._fp.fp.channel``). http.client parsed the response
headers through paramiko's buffered file on that channel, whose ``readline``
reads 8 KB at a time and keeps what follows the headers in ``_rbuffer``. A
short command's whole output arrives in that first read, so docker-py found
nothing left on the channel: ``exec_run`` returned exit 0 and no output at
random, and a curl that had answered read as "no HTTP response".

The exec socket here hands out the buffered bytes before reading the channel.
"""

from __future__ import annotations

from typing import Any

import docker

_SSH_BASE_URL = "http+docker://ssh"


class DockerClient(docker.DockerClient):
    """``docker.DockerClient``, with ``from_env`` and every call unchanged."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.api = _APIClient(*args, **kwargs)


class _APIClient(docker.APIClient):
    def _get_raw_response_socket(self, response: Any) -> Any:
        sock = super()._get_raw_response_socket(response)
        if not self.base_url.startswith(_SSH_BASE_URL):
            return sock
        # The path docker-py itself takes, one step short of the bare channel.
        channel_file = response.raw._fp.fp  # ruff:ignore[private-member-access]
        return _BufferedChannel(channel_file)


class _BufferedChannel:
    """
    A paramiko channel read through its buffered file, read-ahead first.

    ``read(n)`` returns what the file holds, then waits on the channel until it
    has ``n`` bytes or the channel ends: what docker-py's frame reader asks of
    ``recv``. Everything else is the channel's.
    """

    def __init__(self, channel_file: Any) -> None:
        self._file = channel_file
        self._channel = channel_file.channel

    def recv(self, n: int) -> bytes:
        return self._file.read(n)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._channel, name)
