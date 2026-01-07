# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path
from socket import AF_INET, SOCK_STREAM, socket
from subprocess import STDOUT, check_output
from typing import TYPE_CHECKING

from hop3.lib.multi_tail import MultiTail

from .console import log

if TYPE_CHECKING:
    from collections.abc import Iterator


def shell(
    command: str | list[str], cwd: Path | str = "", **kwargs
) -> subprocess.CompletedProcess:
    """Run a shell command with detailed error reporting.

    All output is routed through log() so it gets captured during deployments.

    Args:
        command: Command to execute (string or list of strings)
        cwd: Working directory for the command
        **kwargs: Additional arguments passed to subprocess.run

    Returns:
        CompletedProcess object

    Raises:
        subprocess.CalledProcessError: If command fails, with stdout/stderr included
    """
    match command:
        case str():
            command = command.strip()
        case list():
            command = shlex.join(command)
        case _:
            msg = "command must be a string or a list of strings"
            raise TypeError(msg)

    if cwd:
        cwd = Path(cwd).resolve()
    else:
        cwd = Path.cwd()

    # Log the command (level 2 = verbose)
    log(f"Calling: '{command}' in directory: '{cwd}'", level=2, fg="blue")

    kwargs["shell"] = True
    if cwd:
        kwargs["cwd"] = str(cwd)

    # Capture output for better error messages, but still show it
    if "capture_output" not in kwargs and "stdout" not in kwargs:
        kwargs["capture_output"] = True
        kwargs["text"] = True

    # Allow caller to override check behavior (default: True)
    check = kwargs.pop("check", True)

    try:
        result = subprocess.run(command, **kwargs, check=check)
        # Log captured output (level 2 = verbose, shows with -v flag)
        if result.stdout:
            _log_output(result.stdout, level=2)
        return result
    except subprocess.CalledProcessError as e:
        # Log error information
        log(
            f"Command failed with exit code {e.returncode}: {command}",
            level=0,
            fg="red",
        )
        if e.stdout:
            log("Stdout:", level=1, fg="yellow")
            _log_output(e.stdout, level=1, fg="yellow")
        if e.stderr:
            log("Stderr:", level=1, fg="red")
            _log_output(e.stderr, level=1, fg="red")

        # Re-raise with enhanced message
        raise subprocess.CalledProcessError(
            e.returncode, e.cmd, output=e.stdout, stderr=e.stderr
        ) from e


def _log_output(output: str, level: int = 2, fg: str = "") -> None:
    """Log multi-line output, handling each line separately.

    Args:
        output: The output string to log
        level: Log level (0=important, 1=normal, 2=verbose, 3=debug)
        fg: Foreground color
    """
    for line in output.rstrip().split("\n"):
        log(line, level=level, fg=fg)


def check_binaries(binaries) -> bool:
    """Check if all the binaries exist and are executable.

    Args:
        binaries (list of str): A list of binary names to check for existence and executability.

    Returns:
        bool: True if all binaries are found and executable, False otherwise.
    """
    log(f"Checking requirements: {binaries}", level=3, fg="green")

    # Use shutil.which to determine if the binary exists and is executable
    requirements = [shutil.which(b) for b in binaries]

    # Return True if all binaries are found, otherwise False
    return all(requirements)


def sanitize_app_name(app) -> str:
    """Sanitize the app name by removing invalid characters and trimming
    leading slashes.

    Input:
    - app: A string representing the app name which may contain characters to be sanitized.

    Returns:
    - A sanitized version of the app name string, containing only alphanumeric characters,
      periods, underscores, and hyphens, with leading slashes removed.
    """
    # Filter valid characters (alphanumeric, ".", "_", and "-") from the app name
    # Remove trailing whitespace and leading slashes from the app name
    app = (
        ""
        .join(c for c in app if c.isalnum() or c in {".", "_", "-"})
        .rstrip()
        .lstrip("/")
    )
    return app


def get_free_port(address="") -> int:
    """Find a free TCP port on the host system, selected at random.

    Input:
    - address (str): The IP address to bind to. Defaults to an empty string,
      which signifies binding to all available interfaces.

    Returns:
    - int: A free port number that can be used for TCP connections.
    """
    s = socket(AF_INET, SOCK_STREAM)
    s.bind((address, 0))
    port = s.getsockname()[1]
    s.close()
    return port


def command_output(cmd) -> str:
    """Execute a shell command and retrieve its output as a string.

    Input:
        cmd: A string representing the shell command to execute.

    Returns:
        A string containing the output from the executed command.
        If the command fails or there is no output, an empty string is returned.
    """
    try:
        # Capture the current environment variables
        env = os.environ
        return str(check_output(cmd, stderr=STDOUT, env=env, shell=True))
    except subprocess.CalledProcessError:
        return ""


def multi_tail(filenames, catch_up=20) -> Iterator:
    """Tail multiple log files.

    Input:
    - filenames: List of file names to be tailed.
    - catch_up: Number of lines to read from the end of each file initially (default is 20).

    Returns:
    - An iterator that yields new lines from the specified log files as they are appended.
    """

    tailer = MultiTail(filenames, catch_up)

    # Calls the tail method on the MultiTail instance to start yielding lines
    return tailer.tail()
