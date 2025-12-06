# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Common application management routines for demos."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

from lib.commands import run_hop3
from lib.output import (
    Colors,
    get_output_level,
    pause,
    print_error,
    print_header,
    print_info,
    print_step,
    print_success,
)

if TYPE_CHECKING:
    from lib.context import DemoContext


def deploy_app(ctx: DemoContext, app_name: str, app_dir: Path) -> None:
    """Deploy an application from a directory.

    Args:
        ctx: Demo context
        app_name: Name of the application
        app_dir: Path to the application directory
    """
    print_step(f"Deploying {app_name} application...")
    original_dir = os.getcwd()
    try:
        os.chdir(app_dir)
        run_hop3(f"deploy {app_name}")
    finally:
        os.chdir(original_dir)
    print_success("Application deployed")
    pause(ctx.pause_between_steps)


def set_hostname(ctx: DemoContext, app_name: str, hostname: str) -> None:
    """Set the hostname for an application.

    Args:
        ctx: Demo context
        app_name: Name of the application
        hostname: Hostname to set
    """
    print_step(f"Configuring hostname: {hostname}")
    run_hop3(f"config:set {app_name} HOST_NAME={hostname}")
    print_success(f"Hostname set to {hostname}")
    pause(ctx.pause_between_steps)


def redeploy_app(ctx: DemoContext, app_name: str, app_dir: Path) -> None:
    """Redeploy an application to apply configuration changes.

    Args:
        ctx: Demo context
        app_name: Name of the application
        app_dir: Path to the application directory
    """
    print_step("Redeploying to apply configuration...")
    original_dir = os.getcwd()
    try:
        os.chdir(app_dir)
        run_hop3(f"deploy {app_name}")
    finally:
        os.chdir(original_dir)
    print_success("Application redeployed")
    pause(ctx.pause_between_steps)


def wait_for_app(seconds: int = 3, message: str = "Waiting for application to start...") -> None:
    """Wait for an application to start.

    Args:
        seconds: Number of seconds to wait
        message: Message to display
    """
    print_step(message)
    time.sleep(seconds)


def check_app_status(ctx: DemoContext, app_name: str) -> None:
    """Check and display application status.

    Args:
        ctx: Demo context
        app_name: Name of the application
    """
    print_step("Checking application status...")
    run_hop3(f"app:status {app_name}")
    print_success("Application is running")
    pause(ctx.pause_between_steps)


def test_app_via_curl(
    ctx: DemoContext,
    app_url: str,
    expected_content: str,
) -> None:
    """Test application accessibility via curl.

    Args:
        ctx: Demo context
        app_url: URL to test
        expected_content: Content expected in response

    Raises:
        RuntimeError: If application is not accessible or content doesn't match
    """
    print_step(f"Verifying external access via {app_url}...")
    curl_cmd = f"curl -sk {app_url}/"
    result = subprocess.run(curl_cmd, shell=True, capture_output=True, text=True, check=False)

    if result.returncode == 0 and expected_content in result.stdout:
        if get_output_level() >= 2:  # NORMAL or VERBOSE
            print(f"  {Colors.GREEN}Response:{Colors.RESET}")
            print(f"  {result.stdout.strip()}")
            print()
        print_success(f"Application accessible at {app_url}")
    else:
        print_error(f"Failed to access application at {app_url}")
        if result.stdout:
            print(f"  {Colors.YELLOW}Got response:{Colors.RESET}")
            print(f"  {result.stdout[:200].strip()}")
        raise RuntimeError(f"Application not accessible at {app_url}")

    pause(ctx.pause_between_steps)


def test_app_via_hop3(ctx: DemoContext, app_name: str, app_url: str) -> None:
    """Test application using hop3 app:ping command.

    Args:
        ctx: Demo context
        app_name: Name of the application
        app_url: URL for display purposes
    """
    print_step(f"Testing the application via HTTPS at {app_url}...")
    print_info("Using curl with -k flag to accept self-signed certificate.")
    run_hop3(f"app:ping {app_name}", check=False)
    pause(ctx.pause_between_steps)


def list_apps(ctx: DemoContext) -> None:
    """List all deployed applications.

    Args:
        ctx: Demo context
    """
    print_step("Listing all deployed applications...")
    run_hop3("apps")
    pause(ctx.pause_between_steps)


def show_config(ctx: DemoContext, app_name: str) -> None:
    """Show application configuration/environment variables.

    Args:
        ctx: Demo context
        app_name: Name of the application
    """
    print_step("Viewing environment variables...")
    run_hop3(f"config:show {app_name}")
    pause(ctx.pause_between_steps)


def set_env_vars(ctx: DemoContext, app_name: str, **env_vars: str) -> None:
    """Set environment variables for an application.

    Args:
        ctx: Demo context
        app_name: Name of the application
        **env_vars: Environment variables to set
    """
    print_step("Setting environment variables...")
    vars_str = " ".join(f"{k}={v}" for k, v in env_vars.items())
    run_hop3(f"config:set {app_name} {vars_str}")
    pause(ctx.pause_between_steps)


def restart_app(ctx: DemoContext, app_name: str, wait_seconds: int = 2) -> None:
    """Restart an application and wait.

    Args:
        ctx: Demo context
        app_name: Name of the application
        wait_seconds: Seconds to wait after restart
    """
    print_step("Restarting application...")
    run_hop3(f"app:restart {app_name}")
    time.sleep(wait_seconds)
    print_success("Application restarted")
    pause(ctx.pause_between_steps)


def cleanup_app(ctx: DemoContext, app_name: str, app_url: str) -> None:
    """Cleanup/destroy an application if cleanup is enabled.

    Args:
        ctx: Demo context
        app_name: Name of the application
        app_url: URL for display when skipping cleanup
    """
    if not ctx.no_cleanup:
        print_header("Cleanup")
        print_step(f"Destroying the {app_name} application...")
        run_hop3(f"app:destroy {app_name} -y")
        print_success("Application destroyed")
    else:
        print_info(f"Skipping cleanup. App running at {app_url}")


def show_file_content(
    file_path: Path,
    title: str,
    max_lines: int | None = None,
) -> None:
    """Display the content of a file.

    Args:
        file_path: Path to the file
        title: Title to display
        max_lines: Maximum lines to show (None for all)
    """
    if get_output_level() < 2:  # SILENT or QUIET
        return

    print_step(title)
    if file_path.exists():
        print()
        content = file_path.read_text()
        lines = content.split("\n")
        if max_lines:
            lines = lines[:max_lines]
        for line in lines:
            print(f"  {Colors.DIM}{line}{Colors.RESET}")
        print()


def show_app_structure(app_name: str, files: list[tuple[str, str]]) -> None:
    """Display the application directory structure.

    Args:
        app_name: Name of the application directory
        files: List of (filename, description) tuples
    """
    if get_output_level() < 2:  # SILENT or QUIET
        return

    print_step("Application structure:")
    print()
    print(f"  {Colors.CYAN}{app_name}/{Colors.RESET}")
    for i, (filename, description) in enumerate(files):
        prefix = "└──" if i == len(files) - 1 else "├──"
        print(f"  {prefix} {Colors.GREEN}{filename}{Colors.RESET} - {description}")
    print()
