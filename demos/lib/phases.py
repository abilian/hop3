# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo execution phases."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

from lib.commands import run_hop3
from lib.context import DemoResult, OutputLevel
from lib.discovery import load_demo_module
from lib.logging import (
    capture_failure_debug,
    end_demo_logging,
    get_log_session,
    log_section,
    start_demo_logging,
)
from lib.output import (
    dim,
    pause,
    print_command,
    print_error,
    print_header,
    print_info,
    print_phase_result,
    print_step,
    print_success,
    red,
)

if TYPE_CHECKING:
    from lib.context import DemoContext


def run_prerequisites(ctx: DemoContext) -> bool:
    """Run Phase 1: Prerequisites.

    Args:
        ctx: Demo context

    Returns:
        True on success, False on failure.
    """
    from lib.commands import CommandError
    from lib.server import (
        check_dns_resolution,
        check_hop3_installed,
        check_ubuntu_version,
        clean_server,
        configure_server_settings,
        install_hop3,
        update_hop3_server,
        verify_connectivity,
    )

    print_header("Checking prerequisites", phase=True)

    try:
        verify_connectivity(ctx)
        pause(ctx.pause_between_steps)

        # For SSH backend, check DNS and Ubuntu version
        if ctx.backend == "ssh":
            # Check DNS resolution for demo hostnames (local check, before server checks)
            check_dns_resolution(ctx)
            pause(ctx.pause_between_steps)

            check_ubuntu_version(ctx)
            pause(ctx.pause_between_steps)

        # Clean server if requested (before installation)
        if ctx.clean_before:
            clean_server(ctx)
            pause(ctx.pause_between_steps)

        hop3_installed = check_hop3_installed(ctx)

        if ctx.skip_install:
            if not hop3_installed:
                print_error("Hop3 is not installed and --skip-install was specified")
                print_phase_result(False)
                return False
            print_info("Skipping Hop3 installation/update (--skip-install)")
        elif not hop3_installed:
            install_hop3(ctx)
        else:
            update_hop3_server(ctx)

        # Configure server settings (DEBUG logging, Docker hosts)
        pause(ctx.pause_between_steps)
        configure_server_settings(ctx)

        print_phase_result(True)
        pause(ctx.pause_between_steps)
        return True

    except CommandError as e:
        print_phase_result(False)
        if ctx.verbose:
            print_error(str(e))
        return False


def configure_cli(ctx: DemoContext) -> bool:
    """Run Phase 2: Configure the local Hop3 CLI.

    Args:
        ctx: Demo context

    Returns:
        True on success, False on failure.
    """
    print_header("Configuring CLI", phase=True)

    # Check if hop3 CLI is available
    print_step("Checking hop3 CLI availability...")
    result = subprocess.run(
        "which hop3", shell=True, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        print_error("hop3 CLI not found. Please install it first.")
        print_info("Run: pip install hop3-cli")
        print_phase_result(False)
        return False
    print_success("hop3 CLI found")
    pause(ctx.pause_between_steps)

    # Get server URL based on backend
    backend = ctx.get_backend()
    server_url = backend.get_server_url()

    # Create admin user
    print_step(f"Setting up admin user '{ctx.admin_user}'...")

    if ctx.backend == "docker":
        # For Docker, create admin user directly in the container
        print_info("Creating admin account in Docker container...")
        from lib.commands import run_ssh
        import re

        # Create admin user via hop3-server CLI in container
        # The command outputs an API token that we can use for login
        create_user_cmd = (
            f"echo '{ctx.admin_password}' | "
            f"/home/hop3/venv/bin/hop3-server admin:create "
            f"{ctx.admin_user} {ctx.admin_email} --password-stdin"
        )
        result = run_ssh(ctx, create_user_cmd, check=False, show=False)

        # Extract token from output (admin:create prints a JWT token)
        api_token = None
        if result.returncode == 0:
            # Look for JWT token in output (starts with eyJ)
            token_match = re.search(r'(eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)', result.stdout)
            if token_match:
                api_token = token_match.group(1)

        if result.returncode != 0 and "already exists" not in result.stderr:
            print_error("Failed to create admin user in container")
            if result.stderr:
                print(f"  {red(result.stderr.strip())}")
            print_phase_result(False)
            return False
        print_success(f"Admin user '{ctx.admin_user}' created in container")

        # Configure local CLI to connect to localhost using token-based login
        print_info("Configuring CLI to connect to localhost...")

        if api_token:
            # Use token-based login (more reliable than password)
            login_url = f"{server_url}?token={api_token}"
            config_cmd = f'hop3 login "{login_url}"'
        else:
            # Fallback to password-based login
            config_cmd = (
                f"echo '{ctx.admin_password}' | hop3 login "
                f"--username {ctx.admin_user} "
                f"--server {server_url} "
                f"--password-stdin"
            )

        result = subprocess.run(
            config_cmd, shell=True, capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            print_error("Failed to configure CLI for Docker")
            if result.stderr:
                print(f"  {red(result.stderr.strip())}")
            print_phase_result(False)
            return False
    else:
        # For SSH, use the standard init command
        print_info("This will connect via SSH and create/login the admin account.")

        init_cmd = (
            f"echo '{ctx.admin_password}' | hop3 init "
            f"--ssh {ctx.ssh_target} "
            f"--username {ctx.admin_user} "
            f"--email {ctx.admin_email} "
            f"--server {server_url} "
            f"--password-stdin --yes"
        )
        if ctx.output_level >= OutputLevel.NORMAL:
            print_command(
                f"hop3 init --ssh {ctx.ssh_target} --username {ctx.admin_user} --email {ctx.admin_email}"
            )

        result = subprocess.run(
            init_cmd, shell=True, capture_output=True, text=True, check=False
        )
        if result.stdout and ctx.output_level >= OutputLevel.VERBOSE:
            print(result.stdout)

        if result.returncode != 0:
            if "already exists" in result.stderr:
                print_info("Admin user already exists, attempting login...")
                login_cmd = (
                    f"hop3 login --ssh {ctx.ssh_target} "
                    f"--username {ctx.admin_user} "
                    f"--server {server_url}"
                )
                result = subprocess.run(
                    login_cmd, shell=True, capture_output=True, text=True, check=False
                )
                if result.stdout and ctx.output_level >= OutputLevel.VERBOSE:
                    print(result.stdout)
                if result.returncode != 0:
                    print_error("Failed to login")
                    if result.stderr:
                        print(f"  {red(result.stderr.strip())}")
                    print_phase_result(False)
                    return False
                print_success(f"Logged in as '{ctx.admin_user}'")
            else:
                print_error("Failed to create admin user")
                if result.stderr:
                    print(f"  {red(result.stderr.strip())}")
                print_phase_result(False)
                return False
        else:
            print_success(f"Admin user '{ctx.admin_user}' created")
    pause(ctx.pause_between_steps)

    # Verify authentication (quiet in non-verbose mode)
    print_step("Verifying authentication...")
    try:
        run_hop3("auth:whoami", quiet=(ctx.output_level < OutputLevel.VERBOSE))
    except Exception:
        print_phase_result(False)
        return False
    print_success("Authentication verified")
    print_phase_result(True)

    return True


def run_demo(
    ctx: DemoContext,
    demo_name: str,
    demo_dir: Path,
    is_generic: bool,
) -> DemoResult:
    """Run a single demo.

    Args:
        ctx: Demo context
        demo_name: Display name for the demo
        demo_dir: Path to the demo directory
        is_generic: If True, run generic demo instead of demo-script.py

    Returns:
        DemoResult with status, timing, and error info.
    """
    start_time = time.time()
    title = demo_name
    error_msg = None
    app_name = demo_name  # Default app name for failure capture

    # Start logging for this demo
    start_demo_logging(demo_name)
    log_section("main", f"Starting demo: {demo_name}", f"Demo directory: {demo_dir}\nGeneric: {is_generic}")

    # Show demo start - in quiet mode just "demo1...", in normal mode full header
    if ctx.output_level == OutputLevel.QUIET:
        print(f"{demo_name}... ", end="", flush=True)

    try:
        if is_generic:
            from lib.generic_demo import run_generic_demo

            if ctx.output_level >= OutputLevel.NORMAL:
                print_header(f"Running: {demo_name}")
            run_generic_demo(ctx, demo_dir)
            duration = time.time() - start_time
            if ctx.output_level >= OutputLevel.NORMAL:
                print_success(f"Demo '{demo_name}' completed successfully")
            print_phase_result(True)
            log_section("main", "Demo completed", f"Status: PASS\nDuration: {duration:.2f}s")
            end_demo_logging()
            return DemoResult(
                name=demo_name,
                title=title,
                status="pass",
                duration=duration,
            )
        # Load and run custom demo script
        script_path = demo_dir / "demo-script.py"
        module = load_demo_module(script_path)
        if not module:
            duration = time.time() - start_time
            print_phase_result(False)
            log_section("main", "Demo failed", "Error: Failed to load demo script")
            end_demo_logging()
            return DemoResult(
                name=demo_name,
                title=title,
                status="fail",
                duration=duration,
                error="Failed to load demo script",
            )

        # Get demo info
        title = getattr(module, "TITLE", demo_name)
        description = getattr(module, "DESCRIPTION", "")
        app_name = getattr(module, "APP_NAME", demo_name)
        requires = getattr(module, "REQUIRES", None)

        # Check if demo requirements are satisfied by the current backend
        satisfied, reason = ctx.check_requirements(requires)
        if not satisfied:
            duration = time.time() - start_time
            skip_msg = f"Skipped: {reason}"
            if ctx.output_level >= OutputLevel.NORMAL:
                print_info(f"Skipping {demo_name}: {reason}")
            log_section("main", "Demo skipped", skip_msg)
            end_demo_logging()
            return DemoResult(
                name=demo_name,
                title=title,
                status="skip",
                duration=duration,
                error=skip_msg,
            )

        if ctx.output_level >= OutputLevel.NORMAL:
            print_header(f"Running: {title}")
            if description:
                print(dim(description))
                print()

        # Run demo's main function
        if hasattr(module, "run"):
            module.run(ctx)
            duration = time.time() - start_time
            if ctx.output_level >= OutputLevel.NORMAL:
                print_success(f"Demo '{demo_name}' completed successfully")
            print_phase_result(True)
            log_section("main", "Demo completed", f"Status: PASS\nDuration: {duration:.2f}s")
            end_demo_logging()
            return DemoResult(
                name=demo_name,
                title=title,
                status="pass",
                duration=duration,
            )
        duration = time.time() - start_time
        print_phase_result(False)
        log_section("main", "Demo failed", "Error: Demo has no run() function")
        end_demo_logging()
        return DemoResult(
            name=demo_name,
            title=title,
            status="fail",
            duration=duration,
            error="Demo has no run() function",
        )

    except KeyboardInterrupt:
        print()
        print_error("Demo interrupted by user")
        duration = time.time() - start_time
        log_section("main", "Demo interrupted", "Interrupted by user")
        end_demo_logging()
        return DemoResult(
            name=demo_name,
            title=title,
            status="fail",
            duration=duration,
            error="Interrupted by user",
        )
    except Exception as e:
        error_msg = str(e)
        print_error(f"Demo '{demo_name}' failed: {e}")
        print_phase_result(False)

        # Capture failure debug info (container logs, app info, etc.)
        log_section("main", "Demo failed", f"Error: {error_msg}")
        try:
            capture_failure_debug(ctx, app_name)
        except Exception as capture_err:
            log_section("main", "Failed to capture debug info", str(capture_err))

        # Print log location hint
        log_session = get_log_session()
        if log_session and log_session.current_demo_dir:
            print_info(f"  Logs: {log_session.current_demo_dir}")

        # Log full traceback to file (not console)
        import traceback
        tb_str = traceback.format_exc()
        log_section("traceback", "Exception traceback", tb_str)

        duration = time.time() - start_time
        end_demo_logging()
        return DemoResult(
            name=demo_name,
            title=title,
            status="fail",
            duration=duration,
            error=error_msg,
        )
