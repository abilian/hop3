# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
``listening_ports`` against a *real* procfs — no samples.

The a_unit tests feed :func:`parse_listening_table` recorded ``/proc/net/tcp``
rows, so they pin the parse (hex port at the tail of a hex address, the LISTEN
state column, the inode offset) but never read the kernel's own table or walk
a process's file descriptors. These do: they open real listening sockets and
ask which ports this process holds.

The wiring between the two halves is what only this can catch — that the inode
printed in ``/proc/net/tcp`` is the one ``/proc/<pid>/fd`` links to, and that
IPv6 sockets are attributed like IPv4 ones despite living in a second table
with a wider address column.

Reading procfs is Linux-only; it skips where there is none.
"""

from __future__ import annotations

import os
import socket
import subprocess
from contextlib import closing
from pathlib import Path

import pytest

from hop3.run.listening import listening_ports

pytestmark = pytest.mark.skipif(
    not Path("/proc/net/tcp").exists(), reason="reads /proc/net/tcp (Linux-only)"
)


def _listening(family: int = socket.AF_INET) -> socket.socket:
    """A socket listening on an ephemeral port of ``family``."""
    sock = socket.socket(family)
    sock.bind(("::" if family == socket.AF_INET6 else "0.0.0.0", 0))
    sock.listen(1)
    return sock


def test_a_listening_socket_is_attributed_to_the_process_holding_it():
    with closing(_listening()) as sock:
        port = sock.getsockname()[1]
        assert port in listening_ports([os.getpid()])


def test_an_ipv6_socket_is_found_too():
    """A second table, a 32-hex-digit address, the same attribution."""
    with closing(_listening(socket.AF_INET6)) as sock:
        port = sock.getsockname()[1]
        assert port in listening_ports([os.getpid()])


def test_a_connected_socket_is_not_reported_as_listening():
    """
    Only servers count. A client's port is bound and in /proc/net/tcp, but
    reporting it would name a port the app never served on.
    """
    with closing(_listening()) as server:
        server_port = server.getsockname()[1]
        with closing(socket.create_connection(("127.0.0.1", server_port))) as client:
            ports = listening_ports([os.getpid()])
            assert server_port in ports
            assert client.getsockname()[1] not in ports


def test_a_port_is_attributed_to_its_holder_and_not_to_a_bystander():
    """
    Attribution is per-process, which is the whole point: the diagnosis names
    the ports *this app's* processes hold, not every port on the box.

    The bystander is a child we spawn rather than a well-known pid. An earlier
    version asserted against pid 1 and passed here while failing inside a
    container, where pid 1 was the test process itself.
    """
    bystander = subprocess.Popen(["sleep", "30"])
    try:
        with closing(_listening()) as sock:
            port = sock.getsockname()[1]
            assert port in listening_ports([os.getpid()])
            assert port not in listening_ports([bystander.pid])
    finally:
        bystander.kill()
        bystander.wait()


def test_no_pids_means_no_ports():
    assert listening_ports([]) == set()
