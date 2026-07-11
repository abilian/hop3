# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""The RPC Client routes ``ssh://`` connections through an SshTunnel.

Replaces the old sshtunnel/paramiko compat guard at the Client level: an
``ssh://`` Client must build the tunnel in ``__post_init__``, derive its params
from config, expose the tunnel's local port via ``rpc_url``, and fail loud
(``CliError``) when the tunnel can't start. The SshTunnel itself is stubbed so
no real ssh is spawned.
"""

from __future__ import annotations

import pytest
from hop3_cli.exceptions import CliError
from hop3_cli.rpc import Client
from stubs import StubConfig


class _StubTunnel:
    """Records its construction args; start()/stop() are no-ops."""

    def __init__(self, host, remote_port, *, user, ssh_port=22, key=None, **_kw):
        self.host = host
        self.remote_port = remote_port
        self.user = user
        self.ssh_port = ssh_port
        self.key = key
        self.local_bind_port = 54321
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def is_alive(self) -> bool:
        return self.started and not self.stopped


def test_ssh_client_builds_tunnel_and_derives_params(monkeypatch) -> None:
    monkeypatch.setattr("hop3_cli.rpc.client.SshTunnel", _StubTunnel)

    client = Client(config=StubConfig(api_url="ssh://root@host.example.com"))

    tunnel = client.tunnel
    assert isinstance(tunnel, _StubTunnel)
    assert tunnel.started is True
    # Params derived from the ssh:// URL + config defaults.
    assert tunnel.host == "host.example.com"
    assert tunnel.user == "root"
    assert tunnel.ssh_port == 22
    assert tunnel.remote_port == 8000  # config server_port default
    assert tunnel.key is None
    # RPC is routed through the tunnel's local port.
    assert client.using_ssh_tunnel is True
    assert client.rpc_url == "http://localhost:54321/rpc"

    client.stop()
    assert tunnel.stopped is True
    assert client.tunnel is None


def test_ssh_client_fails_loud_when_tunnel_start_raises(monkeypatch) -> None:
    class _FailingTunnel(_StubTunnel):
        def start(self) -> None:
            msg = "ssh: connect to host port 22: Connection refused"
            raise RuntimeError(msg)

    monkeypatch.setattr("hop3_cli.rpc.client.SshTunnel", _FailingTunnel)

    with pytest.raises(CliError, match="Failed to start SSH tunnel"):
        Client(config=StubConfig(api_url="ssh://root@host.example.com"))


def test_http_client_builds_no_tunnel() -> None:
    client = Client(config=StubConfig(api_url="http://localhost:8000"))
    assert client.tunnel is None
    assert client.using_ssh_tunnel is False
    assert client.rpc_url == "http://localhost:8000/rpc"
