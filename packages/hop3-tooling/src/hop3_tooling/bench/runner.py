# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Command runners: a local shell or an SSH shell on a target.

A runner is a ``Callable[[str], str]`` that executes a shell command and returns
its stdout, raising ``BenchError`` on a non-zero exit — so a failed measurement
step aborts loudly instead of yielding a silent empty string.
"""

from __future__ import annotations

import shlex
import subprocess

from hop3_tooling.bench.probes import BenchError, Runner

_NIX_FLAKES = "experimental-features = nix-command flakes"


def local_runner() -> Runner:
    """Run commands in the local shell."""

    def run(cmd: str) -> str:
        return _exec(["bash", "-c", cmd])

    return run


def ssh_runner(host: str, user: str = "root") -> Runner:
    """Run commands over SSH on ``user@host`` (BatchMode: never prompt)."""

    def run(cmd: str) -> str:
        ssh = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=15",
            f"{user}@{host}",
            f"export NIX_CONFIG={shlex.quote(_NIX_FLAKES)}; {cmd}",
        ]
        return _exec(ssh)

    return run


def _exec(argv: list[str]) -> str:
    result = subprocess.run(argv, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        msg = (
            f"command failed ({result.returncode}): {' '.join(argv)}\n"
            f"{result.stderr.strip()}"
        )
        raise BenchError(msg)
    return result.stdout
