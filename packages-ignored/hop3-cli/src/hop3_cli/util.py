# Copyright (c) 2024-2025, Abilian SAS

"""
Simple client-side script for Hop3.

All the logic is implemented on the server side, this script is just
a thin wrapper around SSH to communicate with the server.
"""

from __future__ import annotations

import subprocess
import sys


def err(*args):
    """Print to stderr."""
    # TODO: rename as this is misleading.
    print(*args, file=sys.stderr)


def dim(text: str) -> str:
    return "\x1b[0;37m" + text + "\x1b[0m"


def run_command(command):
    err(dim(f"Running: {command}"))
    result = subprocess.run(
        command, capture_output=True, shell=True, text=True, check=False
    )
    if result.stderr:
        err(result.stderr)
    return result.stdout.strip()


def run(cmd):
    err(dim(cmd))
    subprocess.run(cmd, shell=True, check=False)
