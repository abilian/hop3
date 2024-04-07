# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS

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
from typing import Iterator

from cleez.colors import dim

from hop3.system.constants import APP_ROOT
from hop3.util.console import Abort, log


def shell(command: str, cwd: Path | str = "", **kwargs) -> int:
    """Run a shell command"""

    if cwd:
        cwd = Path(cwd).resolve()
    else:
        cwd = Path.cwd()

    print(dim(f"Calling: '{command}' in directory: '{cwd}'"))
    sys.stdout.flush()

    kwargs["shell"] = True
    if cwd:
        kwargs["cwd"] = str(cwd)
    return subprocess.call(command, **kwargs)


def check_binaries(binaries) -> bool:
    """Checks if all the binaries exist and are executable"""

    log(f"Checking requirements: {binaries}", level=5, fg="green")
    requirements = [shutil.which(b) for b in binaries]
    return all(requirements)


def sanitize_app_name(app) -> str:
    """Sanitize the app name and build matching path"""

    app = (
        "".join(c for c in app if c.isalnum() or c in (".", "_", "-"))
        .rstrip()
        .lstrip("/")
    )
    return app


def exit_if_invalid(app_name: str) -> str:
    """Utility function for error checking upon command startup."""

    app_name = sanitize_app_name(app_name)
    if not Path(APP_ROOT, app_name).exists():
        raise Abort(f"Error: app '{app_name}' not found.")
    return app_name


def get_free_port(address="") -> int:
    """Find a free TCP port (entirely at random)"""

    s = socket(AF_INET, SOCK_STREAM)
    s.bind((address, 0))  # lgtm [py/bind-socket-all-network-interfaces]
    port = s.getsockname()[1]
    s.close()
    return port


def command_output(cmd) -> str:
    """executes a command and grabs its output, if any"""
    try:
        env = os.environ
        return str(check_output(cmd, stderr=STDOUT, env=env, shell=True))
    except Exception:
        return ""


def multi_tail(app, filenames, catch_up=20) -> Iterator:
    """Tails multiple log files"""

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
    for f in filenames:
        prefixes[f] = os.path.splitext(os.path.basename(f))[0]
        files[f] = open(f, encoding="utf-8", errors="ignore")
        inodes[f] = os.stat(f).st_ino
        files[f].seek(0, 2)

    longest = max(map(len, prefixes.values()))

    # Grab a little history (if any)
    for f in filenames:
        for line in deque(open(f, encoding="utf-8", errors="ignore"), catch_up):
            yield f"{prefixes[f].ljust(longest)} | {line}"

    while True:
        updated = False
        # Check for updates on every file
        for f in filenames:
            line = peek(files[f])
            if line:
                updated = True
                yield f"{prefixes[f].ljust(longest)} | {line}"

        if not updated:
            time.sleep(1)
            # Check if logs rotated
            for f in filenames:
                if os.path.exists(f):
                    if os.stat(f).st_ino != inodes[f]:
                        files[f] = open(f)
                        inodes[f] = os.stat(f).st_ino
                else:
                    filenames.remove(f)
