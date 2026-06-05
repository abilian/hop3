# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Command execution helpers for demos."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

from lib.context import OutputLevel
from lib.logging import log_command, record_timing
from lib.output import get_output_level, print_command, print_error, red

if TYPE_CHECKING:
    from lib.context import DemoContext

# Global debug flag (set by demo.py when --debug is used)
_debug_mode: bool = False

# Env vars the hop3 CLI uses to *steer* resolution (ADR 042, precedence #2 —
# above any stored config). A developer's shell almost always exports these
# (e.g. HOP3_SERVER via direnv) pointing at their real server. If they leak
# into the demo's `hop3` subprocesses they silently override the localhost
# context the demo logs into, so `hop3 deploy` targets the wrong server and
# fails the stream auth (302 -> /auth/login). Strip them so resolution falls
# through to the context the demo established via `hop3 login`.
_CLI_STEERING_ENV_VARS = ("HOP3_SERVER", "HOP3_APP", "HOP3_CONTEXT")

# A demo-private CLI config home. The hop3 CLI stores config.toml / servers.toml
# / state.toml under ``$XDG_CONFIG_HOME/hop3-cli`` (ADR 042). Pointing the demo's
# `hop3` subprocesses at a dedicated dir keeps them off the developer's real
# ~/.config/hop3-cli (which holds their prod/dev contexts): the demo neither
# reads those contexts — so resolution lands cleanly on the demo server it logs
# into — nor clobbers them with its throwaway localhost context.
_DEMO_CLI_CONFIG_HOME = Path(__file__).resolve().parent.parent / ".cli-home"


def cli_env() -> dict[str, str]:
    """Return the environment for local `hop3` CLI calls.

    Two adjustments over the inherited environment:

    - drop the steering vars (see ``_CLI_STEERING_ENV_VARS``) that would
      override the demo's logged-in context;
    - point ``XDG_CONFIG_HOME`` at a demo-private dir so the CLI reads/writes
      an isolated config (see ``_DEMO_CLI_CONFIG_HOME``).
    """
    env = dict(os.environ)
    for var in _CLI_STEERING_ENV_VARS:
        env.pop(var, None)
    env["XDG_CONFIG_HOME"] = str(_DEMO_CLI_CONFIG_HOME)
    return env


def set_debug_mode(*, enabled: bool) -> None:
    """Enable or disable debug mode for hop3 commands."""
    global _debug_mode
    _debug_mode = enabled


def get_debug_mode() -> bool:
    """Check if debug mode is enabled."""
    return _debug_mode


class CommandError(Exception):
    """Raised when a command fails."""

    def __init__(self, message: str, returncode: int = 1):
        super().__init__(message)
        self.returncode = returncode


def run_local(
    cmd: str,
    *,
    show: bool = True,
    check: bool = True,
    log_name: str = "commands",
) -> subprocess.CompletedProcess:
    """Run a command locally.

    Args:
        cmd: Command to run
        show: Whether to show the command in console output
        check: Whether to raise on failure
        log_name: Name of log file to write to (default: "commands")
    """
    if show and get_output_level() >= 2:  # NORMAL or VERBOSE
        print_command(cmd)
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, check=False
    )
    # Always log command execution
    log_command(log_name, cmd, result)

    if check and result.returncode != 0:
        print_error(f"Command failed with exit code {result.returncode}")
        if result.stderr:
            print(f"  {red(result.stderr.strip())}")
        msg = f"Command failed: {cmd}"
        raise CommandError(msg, result.returncode)
    return result


def run_ssh(
    ctx: DemoContext,
    cmd: str,
    *,
    show: bool = True,
    check: bool = True,
    log_name: str = "commands",
) -> subprocess.CompletedProcess:
    """Run a command on the target (SSH server or Docker container).

    Uses the backend from context to run commands, supporting both
    SSH (remote servers) and Docker (local containers).

    Args:
        ctx: Demo context with server/backend connection info
        cmd: Command to run on the target
        show: Whether to show the command in console output
        check: Whether to raise on failure
        log_name: Name of log file to write to (default: "commands")
    """
    # Get backend from context
    backend = ctx.get_backend()
    backend_name = backend.name if hasattr(backend, "name") else "unknown"

    if show and get_output_level() >= 2:  # NORMAL or VERBOSE
        if backend_name == "docker":
            print_command(f"docker exec {ctx.docker_container} '{cmd}'")
        else:
            print_command(f"ssh {ctx.ssh_target} '{cmd}'")

    # Run via backend with timing
    cmd_start = time.time()
    cmd_result = backend.run(cmd, check=False)
    cmd_elapsed = time.time() - cmd_start

    # Record timing for SSH commands
    cmd_short = cmd[:30] + "..." if len(cmd) > 30 else cmd
    record_timing(f"ssh: {cmd_short}", cmd_elapsed, category="ssh")

    # Convert to subprocess.CompletedProcess for compatibility
    result = subprocess.CompletedProcess(
        args=cmd,
        returncode=cmd_result.returncode,
        stdout=cmd_result.stdout,
        stderr=cmd_result.stderr,
    )

    # Log command execution
    if backend_name == "docker":
        log_command(log_name, f"docker exec {ctx.docker_container} '{cmd}'", result)
    else:
        log_command(log_name, f"ssh {ctx.ssh_target} '{cmd}'", result)

    if check and result.returncode != 0:
        print_error(f"Command failed with exit code {result.returncode}")
        # Show both stdout and stderr on failure (installer errors may be in stdout)
        if result.stdout:
            print(f"  {result.stdout.strip()}")
        if result.stderr:
            print(f"  {red(result.stderr.strip())}")
        msg = f"Command failed: {cmd}"
        raise CommandError(msg, result.returncode)
    return result


def run_hop3(
    cmd: str,
    *,
    show: bool = True,
    check: bool = True,
    quiet: bool = False,
    verbose: bool | None = None,
    log_name: str = "hop3-commands",
) -> subprocess.CompletedProcess:
    """Run a hop3 CLI command.

    Args:
        cmd: The hop3 command to run (without 'hop3' prefix)
        show: Whether to show the command being run
        check: Whether to raise on failure
        quiet: If True, suppress stdout output regardless of global level
        verbose: If True, pass -v flag to hop3 for detailed output.
                 If None (default), uses verbose mode when output_level >= VERBOSE
        log_name: Name of log file to write to (default: "hop3-commands")
    """
    output_level = get_output_level()

    # Determine verbosity flags to pass
    # Debug mode (--debug) = maximum verbosity, includes all build logs
    # Verbose mode (-v) = detailed output
    use_debug = _debug_mode
    use_verbose = (
        verbose if verbose is not None else (output_level >= OutputLevel.VERBOSE)
    )

    # Build the command with optional verbose/debug flags
    if use_debug:
        full_cmd = f"hop3 --debug {cmd}"
    elif use_verbose:
        full_cmd = f"hop3 -v {cmd}"
    else:
        full_cmd = f"hop3 {cmd}"

    if show and output_level >= OutputLevel.NORMAL:
        print_command(full_cmd)

    cmd_start = time.time()
    result = subprocess.run(
        full_cmd,
        shell=True,
        capture_output=True,
        text=True,
        check=False,
        env=cli_env(),
    )
    cmd_elapsed = time.time() - cmd_start

    # Record timing for hop3 commands (extract base command for category)
    base_cmd = cmd.split(maxsplit=1)[0] if cmd else "unknown"
    record_timing(f"hop3 {cmd[:40]}", cmd_elapsed, category=f"hop3:{base_cmd}")

    # Always log command execution (including deploy output)
    # Use a more specific log name for deploy commands
    actual_log_name = log_name
    if cmd.startswith("deploy"):
        actual_log_name = "deploy"
    log_command(actual_log_name, full_cmd, result)

    # Print stdout in NORMAL or VERBOSE mode (unless quiet=True)
    if result.stdout and output_level >= OutputLevel.NORMAL and not quiet:
        print(result.stdout)

    if check and result.returncode != 0:
        print_error(f"hop3 command failed with exit code {result.returncode}")
        # Show stdout on failure too - it contains build logs
        if result.stdout and (output_level < OutputLevel.NORMAL or quiet):
            # Only show if we didn't already show it above
            print(result.stdout)
        if result.stderr:
            print(f"  {red(result.stderr.strip())}")
        msg = f"hop3 command failed: {cmd}"
        raise CommandError(msg, result.returncode)
    return result
