# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
import shlex
import shutil
import stat
import subprocess
import time
from pathlib import Path
from socket import AF_INET, SOCK_STREAM, socket
from subprocess import STDOUT, check_output
from typing import TYPE_CHECKING

from hop3.lib.multi_tail import MultiTail

from .console import log

if TYPE_CHECKING:
    from collections.abc import Iterator

# Retry settings for robust deletion
RMTREE_MAX_RETRIES = 3
RMTREE_RETRY_DELAY = 0.1  # seconds


# =============================================================================
# Command execution with proper exceptions
# =============================================================================


class CommandError(Exception):
    """Base exception for command execution failures."""

    def __init__(self, cmd: list[str], message: str) -> None:
        self.cmd = cmd
        self.cmd_str = shlex.join(cmd)
        self.message = message
        super().__init__(f"{self.cmd_str}: {message}")


class CommandNotFoundError(CommandError):
    """Raised when the command executable is not found."""

    def __init__(self, cmd: list[str]) -> None:
        super().__init__(cmd, f"command '{cmd[0]}' not found")


class CommandTimeoutError(CommandError):
    """Raised when the command times out."""

    def __init__(self, cmd: list[str], timeout: int) -> None:
        self.timeout = timeout
        super().__init__(cmd, f"timed out after {timeout}s")


class CommandFailedError(CommandError):
    """Raised when the command returns non-zero exit code."""

    def __init__(self, cmd: list[str], returncode: int, stderr: str = "") -> None:
        self.returncode = returncode
        self.stderr = stderr
        message = f"exited with code {returncode}"
        if stderr:
            message += f" ({stderr})"
        super().__init__(cmd, message)


def run_command(
    cmd: list[str],
    *,
    timeout: int = 10,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    text: bool = False,
) -> subprocess.CompletedProcess:
    """Run a command and return the result, raising on failure.

    Args:
        cmd: Command to execute as a list of strings
        timeout: Timeout in seconds (default: 10)
        cwd: Working directory for the command (default: current directory)
        env: Environment variables for the command (default: inherit from parent)
        text: If True, decode stdout/stderr as text (default: False, returns bytes)

    Returns:
        CompletedProcess on success

    Raises:
        CommandNotFoundError: If the command executable is not found
        CommandTimeoutError: If the command times out
        CommandFailedError: If the command returns non-zero exit code

    Example:
        try:
            result = run_command(["ls", "-la"], cwd="/tmp", text=True)
            print(result.stdout)
        except CommandError as e:
            log(f"Failed: {e}")
    """
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
            text=text,
        )
        return result
    except subprocess.CalledProcessError as e:
        if text:
            stderr = e.stderr.strip() if e.stderr else ""
        else:
            stderr = e.stderr.decode().strip() if e.stderr else ""
        raise CommandFailedError(cmd, e.returncode, stderr) from None
    except FileNotFoundError:
        raise CommandNotFoundError(cmd) from None
    except subprocess.TimeoutExpired:
        raise CommandTimeoutError(cmd, timeout) from None


def try_commands(
    commands: list[tuple[list[str], str]],
    *,
    timeout: int = 10,
) -> str | None:
    """Try multiple commands in sequence until one succeeds.

    This is useful for fallback scenarios where you want to try several
    methods to accomplish the same task (e.g., reloading a service via
    supervisorctl, systemctl, or direct command).

    Args:
        commands: List of (cmd, name) tuples. Each cmd is a list of strings,
                  name is a human-readable description for logging.
        timeout: Timeout in seconds for each command (default: 10)

    Returns:
        The name of the successful command, or None if all failed.

    Raises:
        CommandError: If all commands fail, raises with combined error message.

    Example:
        reload_methods = [
            (["sudo", "-n", "supervisorctl", "restart", "nginx"], "supervisorctl"),
            (["sudo", "-n", "systemctl", "reload", "nginx"], "systemctl"),
            (["sudo", "-n", "nginx", "-s", "reload"], "nginx -s reload"),
        ]
        try:
            method = try_commands(reload_methods)
            log(f"nginx reloaded via {method}")
        except CommandError as e:
            log(f"All reload methods failed: {e}")
    """
    errors = []

    for cmd, name in commands:
        try:
            run_command(cmd, timeout=timeout)
            return name
        except CommandError as e:
            errors.append(f"{name}: {e.message}")

    # All commands failed - raise with combined error message
    error_details = "; ".join(errors)
    raise CommandError([], f"all methods failed: {error_details}")


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


def robust_rmtree(path: Path | str) -> None:
    """Remove a directory tree robustly, handling permission and race condition issues.

    This handles common issues with npm's node_modules, pip's site-packages,
    and similar complex directory structures:
    - Read-only files (common in npm packages and pip packages)
    - Race conditions when files are still being accessed
    - Deep nesting

    Args:
        path: Directory to remove

    Raises:
        OSError: If deletion fails after all retries
    """
    path = Path(path)
    if not path.exists():
        return

    def handle_remove_readonly(func, filepath, exc_info):
        """Error handler that fixes read-only permissions and retries."""
        # If it's a permission error, try to fix permissions and retry
        if isinstance(exc_info[1], PermissionError):
            try:
                os.chmod(filepath, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
                func(filepath)
                return
            except OSError:
                pass
        # Re-raise the original exception
        raise exc_info[1]

    last_error = None
    for attempt in range(RMTREE_MAX_RETRIES):
        try:
            shutil.rmtree(path, onerror=handle_remove_readonly)
            return  # Success
        except OSError as e:
            last_error = e
            if attempt < RMTREE_MAX_RETRIES - 1:
                # Wait a bit before retrying (handles race conditions)
                time.sleep(RMTREE_RETRY_DELAY * (attempt + 1))
            continue

    # All retries failed - try one last time with ignore_errors as fallback
    shutil.rmtree(path, ignore_errors=True)

    # Check if it's really gone
    if path.exists():
        raise last_error or OSError(f"Failed to remove directory: {path}")
