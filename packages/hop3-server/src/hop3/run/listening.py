# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Which TCP ports a set of processes is listening on.

Used to name the most common deploy failure there is: the app ignored
``$PORT``. Hop3 allocates a port per app at deploy time and points the proxy
at it, so an app that binds a port of its own (Grafana's 3000, unless
``GF_SERVER_HTTP_PORT`` is set) starts perfectly, logs "HTTP Server Listen",
and is unreachable. The readiness probe then times out with nothing to say
beyond "did not respond", which sends the operator to raise the one setting
that cannot help.

The evidence is a procfs read away, so we read it: ``/proc/net/tcp{,6}`` gives
every listening socket and its inode, and ``/proc/<pid>/fd`` says which
process holds it. No ``ss``, no ``lsof``, no dependency on a tool being
installed.
"""

from __future__ import annotations

import os
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = ["listening_ports"]

#: ``st`` column value for TCP_LISTEN in /proc/net/tcp (hex, as printed).
_TCP_LISTEN = "0A"

#: Column index of the socket inode in a /proc/net/tcp row.
_INODE_COLUMN = 9


def listening_ports(pids: Iterable[int]) -> set[int]:
    """
    The TCP ports ``pids`` are listening on.

    Returns an empty set where there is no procfs (a non-Linux dev machine) or
    where no socket could be attributed — this feeds a diagnostic message, so
    knowing nothing is a normal outcome and never an error.
    """
    by_inode = _listening_sockets()
    if not by_inode:
        return set()
    ports: set[int] = set()
    for pid in pids:
        ports |= _ports_held_by(pid, by_inode)
    return ports


def _listening_sockets() -> dict[str, int]:
    """Socket inode -> local port, for every TCP socket in LISTEN state."""
    by_inode: dict[str, int] = {}
    for family in ("tcp", "tcp6"):
        try:
            table = Path(f"/proc/net/{family}").read_text()
        except OSError:
            continue  # no procfs, or this family is not configured
        by_inode |= parse_listening_table(table)
    return by_inode


def parse_listening_table(table: str) -> dict[str, int]:
    """
    Socket inode -> local port, from the text of a ``/proc/net/tcp`` table.

    Split from the read (and left importable for its test) so the parsing — a
    hex port at the tail of a hex address, a state column, a fixed inode
    column — can be exercised off Linux; the same parse serves ``tcp`` and
    ``tcp6``. Not part of this module's API: callers want
    :func:`listening_ports`.
    """
    by_inode: dict[str, int] = {}
    for row in table.splitlines()[1:]:  # the first line is the column header
        fields = row.split()
        if len(fields) <= _INODE_COLUMN or fields[3] != _TCP_LISTEN:
            continue
        with suppress(ValueError, IndexError):
            by_inode[fields[_INODE_COLUMN]] = int(fields[1].rsplit(":", 1)[1], 16)
    return by_inode


def _ports_held_by(pid: int, by_inode: dict[str, int]) -> set[int]:
    """The listening ports whose socket this process holds an fd for."""
    try:
        fds = list(Path(f"/proc/{pid}/fd").iterdir())
    except OSError:
        return set()  # exited, or owned by another user
    ports: set[int] = set()
    for fd in fds:
        target = ""
        with suppress(OSError):
            target = os.readlink(fd)  # exited between listing and read
        if not target.startswith("socket:["):
            continue
        inode = target.removeprefix("socket:[").removesuffix("]")
        port = by_inode.get(inode)
        if port is not None:
            ports.add(port)
    return ports
