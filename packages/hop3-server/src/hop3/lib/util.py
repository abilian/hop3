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
from typing import TYPE_CHECKING, assert_never

from hop3.lib.multi_tail import MultiTail

__all__ = [
    "CommandError",
    "CommandFailedError",
    "CommandNotFoundError",
    "CommandTimeoutError",
    "check_binaries",
    "command_output",
    "get_free_port",
    "is_port_free",
    "log_command_stream",
    "multi_tail",
    "robust_rmtree",
    "run_command",
    "sanitize_app_name",
    "shell",
    "try_commands",
]

from .console import log
from .sh import log_command_stream, shell

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

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

    def __init__(self, cmd: list[str], timeout: float) -> None:
        self.timeout = timeout
        super().__init__(cmd, f"timed out after {timeout}s")


class CommandFailedError(CommandError):
    """Raised when the command returns non-zero exit code."""

    def __init__(
        self,
        cmd: list[str],
        returncode: int,
        stderr: str = "",
        stdout: str = "",
    ) -> None:
        self.returncode = returncode
        self.stderr = stderr
        # Captured stdout. Many tools write their real error (and tracebacks) to
        # stdout, not stderr, so callers that only surface stderr would show a
        # bare exit code. Kept on the exception so they can surface both.
        self.stdout = stdout
        message = f"exited with code {returncode}"
        if stderr:
            message += f" ({stderr})"
        super().__init__(cmd, message)


def run_command(
    cmd: list[str],
    *,
    timeout: float = 10,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    text: bool = False,
    input: str | bytes | None = None,
) -> subprocess.CompletedProcess:
    """
    Run a command and return the result, raising on failure.

    Args:
        cmd: Command to execute as a list of strings
        timeout: Timeout in seconds (default: 10)
        cwd: Working directory for the command (default: current directory)
        env: Environment variables for the command (default: inherit from parent)
        text: If True, decode stdout/stderr as text (default: False, returns bytes)
        input: Data to send to command's stdin (default: None)

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
            input=input,
        )
        return result
    except subprocess.CalledProcessError as e:
        if text:
            stderr = e.stderr.strip() if e.stderr else ""
            stdout = e.stdout.strip() if e.stdout else ""
        else:
            stderr = e.stderr.decode().strip() if e.stderr else ""
            stdout = e.stdout.decode().strip() if e.stdout else ""
        raise CommandFailedError(cmd, e.returncode, stderr, stdout) from None
    except FileNotFoundError:
        raise CommandNotFoundError(cmd) from None
    except subprocess.TimeoutExpired:
        raise CommandTimeoutError(cmd, timeout) from None


def try_commands(
    commands: list[tuple[list[str], str]],
    *,
    timeout: float = 10,
) -> str | None:
    """
    Try multiple commands in sequence until one succeeds.

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

    NOT for privileged operations. Service reloads and anything else needing
    root go through hop3-rootd (``hop3.lib.rootd.reload_service``): `sudo -n`
    fails outright where the hop3 user has no passwordless sudo, and the
    privilege model keeps privileged work behind the daemon rather than in a
    growing list of sudo shortcuts. This helper is for unprivileged probes.

    Example:
        detect_methods = [
            (["git", "--version"], "git"),
            (["hg", "--version"], "mercurial"),
        ]
        try:
            vcs = try_commands(detect_methods)
        except CommandError as e:
            log(f"No supported VCS found: {e}")
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


def check_binaries(binaries: list[str]) -> bool:
    """
    Check if all the binaries exist and are executable.

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


def sanitize_app_name(app: str) -> str:
    """
    Sanitize the app name by removing invalid characters and trimming
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


def is_port_free(port: int, address: str = "127.0.0.1") -> bool:
    """
    Check if a TCP port is free (not in use).

    Args:
        port: The port number to check.
        address: The IP address to check on. Defaults to localhost.

    Returns:
        True if the port is free, False if it's in use.
    """
    s = socket(AF_INET, SOCK_STREAM)
    try:
        s.bind((address, port))
        s.close()
        return True
    except OSError:
        return False


def get_free_port(address: str = "") -> int:
    """
    Find a free TCP port on the host system, selected at random.

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


def command_output(cmd: str | list[str]) -> str:
    """
    Execute a command and retrieve its output as a string.

    Args:
        cmd: Command to execute (string or list of strings).
             Strings are safely parsed with shlex.split().

    Returns:
        A string containing the output from the executed command.
        If the command fails or there is no output, an empty string is returned.
    """
    try:
        # Parse string commands safely without shell=True
        match cmd:
            case str():
                cmd_list = shlex.split(cmd)
            case list():
                cmd_list = cmd
            case _ as unreachable:
                assert_never(unreachable)
        env = os.environ
        result = check_output(cmd_list, stderr=STDOUT, env=env)
        return result.decode("utf-8", errors="replace")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def multi_tail(filenames: list[str | Path], catch_up: int = 20) -> Iterator[str]:
    """
    Tail multiple log files.

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
    """
    Remove a directory tree robustly, handling permission and race condition issues.

    This handles common issues with npm's node_modules, pip's site-packages,
    and similar complex directory structures:
    - Read-only files (common in npm packages and pip packages)
    - Race conditions when files are still being accessed
    - Deep nesting
    - Symbolic links (which shutil.rmtree cannot handle)

    Args:
        path: Directory to remove

    Raises:
        OSError: If deletion fails after all retries
    """
    path = Path(path)
    if not path.exists() and not path.is_symlink():
        return

    # Handle symlinks - shutil.rmtree raises "Cannot call rmtree on a symbolic link"
    if path.is_symlink():
        path.unlink()
        return

    def handle_remove_readonly(
        func: Callable[..., object], filepath: str, exc: BaseException
    ) -> None:
        """Error handler that fixes read-only permissions and retries."""
        # If it's a permission error, try to fix permissions and retry
        if isinstance(exc, PermissionError):
            try:
                os.chmod(filepath, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
                func(filepath)
                return
            except OSError:
                pass
        # Re-raise the original exception
        raise exc

    last_error = None
    for attempt in range(RMTREE_MAX_RETRIES):
        try:
            shutil.rmtree(path, onexc=handle_remove_readonly)
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
