# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Reading listening ports out of a ``/proc/net/tcp`` table.

The parse is what can be wrong here — the port is hex and at the tail of a hex
address, the state column decides whether a row counts, and the inode is at a
fixed offset in a row that keeps going for several more fields. The samples
below are real rows, trimmed only of their trailing kernel pointers.
"""

from __future__ import annotations

from hop3.run.listening import parse_listening_table

# 1F90 = 8080, 0BB8 = 3000, C350 = 50000.
TCP4 = """\
  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 00000000:1F90 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 123456 1 0000 100 0 0 10 0
   1: 0100007F:0BB8 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 123457 1 0000 100 0 0 10 0
   2: 0100007F:0BB8 0100007F:C350 01 00000000:00000000 00:00000000 00000000  1000        0 123458 1 0000 100 0 0 10 0
"""

TCP6 = """\
  sl  local_address                         remote_address                        st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 00000000000000000000000000000000:1F91 00000000000000000000000000000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 223456 1 0000 100 0 0 10 0
"""


def test_a_listening_socket_yields_its_port():
    assert parse_listening_table(TCP4)["123456"] == 8080


def test_an_established_connection_is_not_a_listening_socket():
    """Row 2 is a client connection to :3000, not a server on it."""
    assert "123458" not in parse_listening_table(TCP4)


def test_the_header_row_is_not_parsed_as_a_socket():
    assert len(parse_listening_table(TCP4)) == 2


def test_ipv6_rows_parse_despite_the_longer_address():
    """The port is the tail of the address whatever the address's width."""
    assert parse_listening_table(TCP6) == {"223456": 8081}


def test_an_empty_table_is_not_an_error():
    assert parse_listening_table("") == {}


def test_a_truncated_row_is_skipped_rather_than_crashing():
    """procfs is read live; a row can be short if the socket is going away."""
    truncated = TCP4 + "   3: 0100007F:1F92 00000000:0000 0A\n"
    assert parse_listening_table(truncated) == {"123456": 8080, "123457": 3000}
