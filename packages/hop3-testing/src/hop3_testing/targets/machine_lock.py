# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
One e2e session per machine, enforced rather than documented.

The Docker target has a fixed container name and fixed ports, so a second run
started beside the first tears its container down mid-install (2026-10-13: an
install SIGKILLed, exit 137, by a run another session had just started). A run
takes this lock before touching Docker; the kernel releases it when the holder
exits, however it exits, so a crashed run never leaves a stale lock.

The lock is re-entrant within a process: pytest's session fixture holds it,
and a Docker target the same session starts takes it again.
"""

from __future__ import annotations

import fcntl
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

LOCK_PATH = Path.home() / ".hop3" / "docker-target.lock"

#: This process's open lock file and its number of holders, per lock path.
_held: dict[Path, tuple[TextIO, int]] = {}


class MachineBusyError(RuntimeError):
    """Another run holds the Docker target; the message names it."""


@dataclass
class DockerTargetHold:
    """One holder's share of the lock; the last one to close releases it."""

    path: Path
    closed: bool = False

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        handle, count = _held[self.path]
        if count > 1:
            _held[self.path] = (handle, count - 1)
            return
        del _held[self.path]
        handle.close()


def hold_docker_target(path: Path = LOCK_PATH) -> DockerTargetHold:
    """
    Take the machine's Docker-target lock, or raise naming who holds it.

    Keep the returned hold open for the whole run: closing the last hold
    releases the lock.
    """
    if path in _held:
        handle, count = _held[path]
        _held[path] = (handle, count + 1)
        return DockerTargetHold(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.seek(0)
        holder = handle.read().strip() or "unknown"
        handle.close()
        msg = (
            f"another e2e session is using the Docker target ({holder}). One "
            "e2e session per machine: its container and ports are shared, and "
            "starting now would tear its container down. Wait for it to end."
        )
        raise MachineBusyError(msg) from None
    handle.seek(0)
    handle.truncate()
    handle.write(f"pid {os.getpid()}: {' '.join(sys.argv)}")
    handle.flush()
    _held[path] = (handle, 1)
    return DockerTargetHold(path)
