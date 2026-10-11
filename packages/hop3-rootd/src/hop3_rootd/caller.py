# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Whether a connecting process runs inside the app runtime.

Every native app runs as ``hop3``, the uid this daemon admits, so the uid check
alone let any app's code call every op: root, with no exploit. Until each app
has its own user (ADR 055, planned for 0.9), the caller's *place* tells them
apart. Apps are the uWSGI Emperor's vassals and everything they start; the
control plane (hop3-server, a git-push deploy, an operator's ``hop3-server``
command) is not under the Emperor.

- **Under systemd**, the Emperor's unit is a cgroup its descendants cannot leave
  without privileges they do not have: a caller in it is refused, and so is one
  in ``hop3.slice``, where an app with native limits is moved.
- **Without systemd** (the Docker target, under supervisor), there are no
  per-service cgroups, so the caller's ancestry is walked for the Emperor. This
  is weaker: a process that double-forks is reparented away from the Emperor and
  passes. Production servers run systemd.

A caller whose ``/proc`` entries cannot be read is refused: the check fails
closed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from hop3_rootd.cgroup import HOP3_SLICE

#: The systemd unit the uWSGI Emperor, and so every app, runs in.
APP_RUNTIME_UNIT: Final[str] = "uwsgi-hop3.service"

#: The cgroups an app runs in: the Emperor's unit, and the slice whose scopes
#: hold an app with native limits (`cgroup.attach_pids` moves it there, out of
#: the Emperor's unit; the slice holds nothing else).
_APP_CGROUPS: Final[frozenset[str]] = frozenset({APP_RUNTIME_UNIT, HOP3_SLICE})

#: How the Emperor shows on its command line, on a host without systemd.
_EMPEROR_FLAG: Final[bytes] = b"--emperor"

_PROC: Final[Path] = Path("/proc")


def in_app_runtime(pid: int, proc: Path = _PROC) -> bool:
    """True when ``pid`` runs inside the app runtime, or cannot be placed."""
    try:
        cgroups = (proc / str(pid) / "cgroup").read_text()
    except OSError:
        return True
    paths = [line.split(":", 2)[-1] for line in cgroups.splitlines() if line]
    if any(path != "/" for path in paths):
        # A process manager placed it: the cgroup says where.
        return any(_APP_CGROUPS & set(path.split("/")) for path in paths)
    return _descends_from_emperor(pid, proc)


def _descends_from_emperor(pid: int, proc: Path) -> bool:
    """Walk the parents of ``pid``; True if one is the uWSGI Emperor."""
    seen: set[int] = set()
    while pid > 1 and pid not in seen:
        seen.add(pid)
        try:
            argv = (proc / str(pid) / "cmdline").read_bytes().split(b"\0")
            stat = (proc / str(pid) / "stat").read_text()
        except OSError:
            return True
        if _EMPEROR_FLAG in argv:
            return True
        # `pid (comm) state ppid ...`: comm may hold spaces and parentheses,
        # so the fields are read after its last `)`.
        pid = int(stat.rsplit(")", 1)[1].split()[1])
    return False
