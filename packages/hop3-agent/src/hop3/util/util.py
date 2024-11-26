# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from socket import AF_INET, SOCK_STREAM, socket
from subprocess import STDOUT, check_output
from typing import TYPE_CHECKING

from hop3.util.multi_tail import MultiTail

from .console import dim, log

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
    return subprocess.run(command, **kwargs, check=True)


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

    tailer = MultiTail(filenames, catch_up)
    return tailer.tail()
