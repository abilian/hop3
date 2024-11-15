# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from collections import deque
from pathlib import Path
from socket import AF_INET, SOCK_STREAM, socket
from subprocess import STDOUT, check_output
from typing import TYPE_CHECKING

from cleez.colors import dim

from .console import log

if TYPE_CHECKING:
    from collections.abc import Iterator


def shell(command: str, cwd: Path | str = "", **kwargs) -> subprocess.CompletedProcess:
    """Run a shell command."""
    if cwd:
        cwd = Path(cwd).resolve()
    else:
        cwd = Path.cwd()

    print(dim(f"Calling: '{command}' in directory: '{cwd}'"))
    sys.stdout.flush()

    kwargs["shell"] = True
    if cwd:
        kwargs["cwd"] = str(cwd)
    return subprocess.run(command, **kwargs, check=False)


def check_binaries(binaries) -> bool:
    """Check if all the binaries exist and are executable."""
    log(f"Checking requirements: {binaries}", level=5, fg="green")
    requirements = [shutil.which(b) for b in binaries]
    return all(requirements)


def sanitize_app_name(app) -> str:
    """Sanitize the app name and build matching path."""
    app = (
        "".join(c for c in app if c.isalnum() or c in {".", "_", "-"})
        .rstrip()
        .lstrip("/")
    )
    return app


def get_free_port(address="") -> int:
    """Find a free TCP port (entirely at random)."""
    s = socket(AF_INET, SOCK_STREAM)
    s.bind((address, 0))  # lgtm [py/bind-socket-all-network-interfaces]
    port = s.getsockname()[1]
    s.close()
    return port


def command_output(cmd) -> str:
    """Execute a command and grabs its output, if any."""
    try:
        env = os.environ
        return str(check_output(cmd, stderr=STDOUT, env=env, shell=True))
    except Exception:
        return ""


def multi_tail(filenames, catch_up=20) -> Iterator:
    """Tails multiple log files."""

    # Seek helper
    def peek(handle):
        where = handle.tell()
        line = handle.readline()
        if not line:
            handle.seek(where)
            return None
        return line

    inodes = {}
    files = {}
    prefixes = {}

    # Set up current state for each log file
    for filename in filenames:
        path = Path(filename)
        prefixes[filename] = path.stem
        inodes[filename] = path.stat().st_ino
        files[filename] = path.open()
        files[filename].seek(0, 2)

    longest = max(map(len, prefixes.values()))

    # Grab a little history (if any)
    for filename in filenames:
        filepath = Path(filename)
        for line in deque(filepath.open(errors="ignore"), catch_up):
            yield f"{prefixes[filename].ljust(longest)} | {line}"

    while True:
        updated = False
        # Check for updates on every file
        for filename in filenames:
            line = peek(files[filename])
            if line:
                updated = True
                yield f"{prefixes[filename].ljust(longest)} | {line}"

        if not updated:
            time.sleep(1)
            # Check if logs rotated
            for filename in filenames:
                filepath = Path(filename)
                if filepath.exists():
                    if filepath.stat().st_ino != inodes[filename]:
                        files[filename] = filepath.open()
                        inodes[filename] = filepath.stat().st_ino
                else:
                    filenames.remove(filename)
