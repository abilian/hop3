from __future__ import annotations

import subprocess

from .console import dim, err


def run_command(command):
    result = subprocess.run(
        command, capture_output=True, shell=True, text=True, check=False
    )
    if result.stderr:
        err(result.stderr)
    return result.stdout.strip()


def run(cmd):
    err(dim(cmd))
    subprocess.run(cmd, shell=True, check=False)
