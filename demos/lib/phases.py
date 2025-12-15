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
        check_hop3_installed,
        check_ubuntu_version,
        clean_server,
        configure_server_settings,
        install_hop3,
        update_hop3_server,
        verify_ssh_access,
    )

    print_header("Checking prerequisites", phase=True)

    try:
        verify_ssh_access(ctx)
        pause(ctx.pause_between_steps)

        # Clean server if requested (before checking ubuntu version)
        if ctx.clean_before:
            clean_server(ctx)
            pause(ctx.pause_between_steps)

        check_ubuntu_version(ctx)
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

    # Create admin user via SSH
    print_step(f"Setting up admin user '{ctx.admin_user}'...")
    print_info("This will connect via SSH and create/login the admin account.")

    init_cmd = (
        f"echo '{ctx.admin_password}' | hop3 init "
        f"--ssh {ctx.ssh_target} "
        f"--username {ctx.admin_user} "
        f"--email {ctx.admin_email} "
        f"--server http://{ctx.server_ip}:8000 "
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
                f"--server http://{ctx.server_ip}:8000"
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
            return DemoResult(
                name=demo_name,
                title=title,
                status="pass",
                duration=duration,
            )
        duration = time.time() - start_time
        print_phase_result(False)
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
        if ctx.verbose:
            import traceback

            traceback.print_exc()
        duration = time.time() - start_time
        return DemoResult(
            name=demo_name,
            title=title,
            status="fail",
            duration=duration,
            error=error_msg,
        )
