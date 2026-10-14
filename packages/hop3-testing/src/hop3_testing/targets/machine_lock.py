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
"""

from __future__ import annotations

import fcntl
import os
import sys
from pathlib import Path
from typing import TextIO

LOCK_PATH = Path.home() / ".hop3" / "docker-target.lock"


class MachineBusyError(RuntimeError):
    """Another run holds the Docker target; the message names it."""


def hold_docker_target(path: Path = LOCK_PATH) -> TextIO:
    """
    Take the machine's Docker-target lock, or raise naming who holds it.

    Keep the returned file open for the whole run: closing it releases the
    lock.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.seek(0)
        holder = handle.read().strip() or "unknown"
        handle.close()
        msg = (
            f"another hop3-test run is using the Docker target ({holder}). One "
            "e2e session per machine: its container and ports are shared, and "
            "starting now would tear its container down. Wait for it to end."
        )
        raise MachineBusyError(msg) from None
    handle.seek(0)
    handle.truncate()
    handle.write(f"pid {os.getpid()}: {' '.join(sys.argv)}")
    handle.flush()
    return handle
