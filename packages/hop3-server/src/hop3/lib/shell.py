# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Shell command execution with detailed error reporting."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from .console import log

__all__ = ["shell"]

# Shell operators that require wrapping in sh -c
_SHELL_OPERATORS = {"&&", "||", ";", "|", ">", ">>", "<", "$("}


def shell(
    command: str | list[str], cwd: Path | str = "", **kwargs
) -> subprocess.CompletedProcess:
    """Run a command with detailed error reporting.

    All output is routed through log() so it gets captured during deployments.
    Commands are executed safely without shell=True to prevent injection attacks.

    Args:
        command: Command to execute (string or list of strings).
                 Strings are safely parsed with shlex.split().
        cwd: Working directory for the command
        **kwargs: Additional arguments passed to subprocess.run

    Returns:
        CompletedProcess object

    Raises:
        subprocess.CalledProcessError: If command fails, with stdout/stderr included
    """
    command_display, command_list = _parse_command(command)
    cwd = _resolve_cwd(cwd)

    log(f"Calling: '{command_display}' in directory: '{cwd}'", level=2, fg="blue")

    if cwd:
        kwargs["cwd"] = str(cwd)

    # Capture output for better error messages, but still show it
    if "capture_output" not in kwargs and "stdout" not in kwargs:
        kwargs["capture_output"] = True
        kwargs["text"] = True

    # Allow caller to override check behavior (default: True)
    check = kwargs.pop("check", True)

    try:
        result = subprocess.run(command_list, **kwargs, check=check)
        if result.stdout:
            _log_output(result.stdout, level=2)
        return result
    except subprocess.CalledProcessError as e:
        _log_error(command_display, e)
        raise subprocess.CalledProcessError(
            e.returncode, e.cmd, output=e.stdout, stderr=e.stderr
        ) from e


def _parse_command(command: str | list[str]) -> tuple[str, list[str]]:
    """Parse command into display string and argument list.

    Strings with shell operators are wrapped in ``sh -c``.
    """
    match command:
        case str():
            display = command.strip()
            if _needs_shell(display):
                return display, ["sh", "-c", display]
            return display, shlex.split(display)
        case list():
            return shlex.join(command), command
        case _:
            msg = "command must be a string or a list of strings"
            raise TypeError(msg)


def _needs_shell(command: str) -> bool:
    """Check if command contains shell operators requiring sh -c."""
    if any(op in command for op in _SHELL_OPERATORS):
        return True
    # Check for env var assignment pattern (e.g., "CI=true bin/script.sh")
    first_token = command.split(maxsplit=1)[0] if command.split() else ""
    return "=" in first_token


def _resolve_cwd(cwd: Path | str) -> Path:
    """Resolve the working directory."""
    if cwd:
        return Path(cwd).resolve()
    return Path.cwd()


def _log_error(
    command_display: str, e: subprocess.CalledProcessError
) -> None:
    """Log details of a failed command."""
    log(
        f"Command failed with exit code {e.returncode}: {command_display}",
        level=0,
        fg="red",
    )
    if e.stdout:
        log("Stdout:", level=1, fg="yellow")
        _log_output(e.stdout, level=1, fg="yellow")
    if e.stderr:
        log("Stderr:", level=1, fg="red")
        _log_output(e.stderr, level=1, fg="red")


def _log_output(output: str, level: int = 2, fg: str = "") -> None:
    """Log multi-line output, handling each line separately."""
    for line in output.rstrip().split("\n"):
        log(line, level=level, fg=fg)
