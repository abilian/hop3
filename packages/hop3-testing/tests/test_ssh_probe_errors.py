# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""A failed SSH connectivity check says why, instead of a bare False."""

from __future__ import annotations

import socket

import pytest
from hop3_testing.util.ssh import (
    SSHConnection,
    SSHConnectionInfo,
    is_port_open,
    verify_ssh_connectivity,
    wait_for_ssh,
)


def _closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_open_port_passes():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        probe = is_port_open("127.0.0.1", s.getsockname()[1])
    assert probe
    assert probe.error is None


def test_closed_port_carries_the_refusal():
    port = _closed_port()
    probe = is_port_open("127.0.0.1", port, timeout=2)
    assert not probe
    assert f"127.0.0.1:{port}" in probe.error
    assert "ConnectionRefusedError" in probe.error


def test_wait_for_ssh_timeout_carries_the_last_error():
    port = _closed_port()
    probe = wait_for_ssh("127.0.0.1", port=port, timeout=1, interval=0)
    assert not probe
    assert "not ready after 1s" in probe.error
    assert "ConnectionRefusedError" in probe.error


def test_connect_failure_is_recorded_and_propagated():
    port = _closed_port()
    conn = SSHConnection(SSHConnectionInfo(host="127.0.0.1", port=port))
    connected = conn.connect(timeout=2)
    assert not connected
    assert f"root@127.0.0.1:{port}" in str(connected.error)
    with pytest.raises(ConnectionError, match=f"root@127.0.0.1:{port}"), conn:
        pass

    probe = verify_ssh_connectivity("127.0.0.1", port=port, timeout=2)
    assert not probe
    assert f"root@127.0.0.1:{port}" in probe.error
