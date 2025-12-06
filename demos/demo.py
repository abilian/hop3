#!/usr/bin/env python3
# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Unified Hop3 Demo Script.

Run one or more demos on a target server.

Usage:
    python demo.py <server_ip> [demo_names...] [options]

Examples:
    python demo.py 46.62.169.221                    # Run all demos
    python demo.py 46.62.169.221 demo1              # Run demo1 only
    python demo.py 46.62.169.221 demo1 demo2        # Run demo1 then demo2
    python demo.py 46.62.169.221 --local            # Use local code via rsync
    python demo.py 46.62.169.221 --skip-install     # Skip Hop3 installation
    python demo.py 46.62.169.221 --no-cleanup       # Keep apps after demo
"""

from __future__ import annotations

import argparse
import secrets
import subprocess
import sys
from pathlib import Path

# Add demos directory to path for imports
DEMOS_DIR = Path(__file__).parent
sys.path.insert(0, str(DEMOS_DIR))

from lib import DemoContext
from lib.output import (
    Colors,
    pause,
    print_error,
    print_header,
    print_info,
    print_success,
)


def discover_demos() -> list[str]:
    """Discover available demos by scanning subdirectories."""
    demos = []
    for path in sorted(DEMOS_DIR.iterdir()):
        if path.is_dir() and path.name.startswith("demo"):
            script = path / "demo-script.py"
            if script.exists():
                demos.append(path.name)
    return demos


def load_demo(demo_name: str):
    """Load a demo script module."""
    try:
        # Import demo-script.py using importlib with spec
        import importlib.util

        script_path = DEMOS_DIR / demo_name / "demo-script.py"
        spec = importlib.util.spec_from_file_location(f"{demo_name}.demo_script", script_path)
        if spec is None or spec.loader is None:
            print_error(f"Failed to load demo '{demo_name}': Could not find demo-script.py")
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        print_error(f"Failed to load demo '{demo_name}': {e}")
        return None


def print_banner() -> None:
    """Print the demo banner."""
    banner = """
    ╦ ╦╔═╗╔═╗┌─┐  ╔╦╗┌─┐┌┬┐┌─┐┌─┐
    ╠═╣║ ║╠═╝ ─┤   ║║├┤ ││││ │└─┐
    ╩ ╩╚═╝╩  └─┘  ═╩╝└─┘┴ ┴└─┘└─┘

    Hop3 Demo Runner
    ================
    """
    print(f"{Colors.CYAN}{Colors.BOLD}{banner}{Colors.RESET}")


def print_config(ctx: DemoContext, demos: list[str]) -> None:
    """Print demo configuration."""
    print(f"{Colors.BOLD}Configuration:{Colors.RESET}")
    print(f"  Server IP:       {ctx.server_ip}")
    print(f"  SSH Target:      {ctx.ssh_target}")
    print(f"  Admin User:      {ctx.admin_user}")
    print(f"  Demos to run:    {', '.join(demos)}")
    print(f"  Use local code:  {ctx.use_local_code}")
    print(f"  Skip install:    {ctx.skip_install}")
    print(f"  No cleanup:      {ctx.no_cleanup}")
    print()


def configure_cli(ctx: DemoContext) -> None:
    """Configure the local Hop3 CLI."""
    from lib.commands import run_hop3
    from lib.output import print_command, print_step

    print_header("Configuring Hop3 CLI")

    # Check if hop3 CLI is available
    print_step("Checking hop3 CLI availability...")
    result = subprocess.run(
        "which hop3", shell=True, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        print_error("hop3 CLI not found. Please install it first.")
        print_info("Run: pip install hop3-cli")
        sys.exit(1)
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
    print_command(
        f"hop3 init --ssh {ctx.ssh_target} --username {ctx.admin_user} --email {ctx.admin_email}"
    )

    result = subprocess.run(
        init_cmd, shell=True, capture_output=True, text=True, check=False
    )
    if result.stdout:
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
            if result.stdout:
                print(result.stdout)
            if result.returncode != 0:
                print_error("Failed to login")
                if result.stderr:
                    print(f"  {Colors.RED}{result.stderr.strip()}{Colors.RESET}")
                sys.exit(1)
            print_success(f"Logged in as '{ctx.admin_user}'")
        else:
            print_error("Failed to create admin user")
            if result.stderr:
                print(f"  {Colors.RED}{result.stderr.strip()}{Colors.RESET}")
            sys.exit(1)
    else:
        print_success(f"Admin user '{ctx.admin_user}' created")
    pause(ctx.pause_between_steps)

    # Verify authentication
    print_step("Verifying authentication...")
    run_hop3("auth:whoami")
    print_success("Authentication verified")


def run_demo(ctx: DemoContext, demo_name: str) -> bool:
    """Run a single demo.

    Returns:
        True if demo completed successfully, False otherwise.
    """
    manifest = load_demo(demo_name)
    if not manifest:
        return False

    # Print demo banner
    title = getattr(manifest, "TITLE", demo_name)
    description = getattr(manifest, "DESCRIPTION", "")

    print_header(f"Running: {title}")
    if description:
        print(f"{Colors.DIM}{description}{Colors.RESET}")
        print()

    try:
        # Run demo's main function
        if hasattr(manifest, "run"):
            manifest.run(ctx)
            print_success(f"Demo '{demo_name}' completed successfully")
            return True
        else:
            print_error(f"Demo '{demo_name}' has no run() function")
            return False
    except KeyboardInterrupt:
        print()
        print_error("Demo interrupted by user")
        return False
    except Exception as e:
        print_error(f"Demo '{demo_name}' failed: {e}")
        if ctx.verbose:
            import traceback

            traceback.print_exc()
        return False


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    available_demos = discover_demos()

    parser = argparse.ArgumentParser(
        description="Hop3 Demo Runner - Run demos on a target server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Available demos: {", ".join(available_demos) if available_demos else "(none found)"}

Examples:
  python demo.py 46.62.169.221                    # Run all demos
  python demo.py 46.62.169.221 demo1              # Run demo1 only
  python demo.py 46.62.169.221 demo1 demo2        # Run multiple demos
  python demo.py 46.62.169.221 --local            # Use local code via rsync
  python demo.py 46.62.169.221 --skip-install     # Skip Hop3 installation
        """,
    )

    parser.add_argument(
        "server_ip",
        help="IP address of the target server",
    )
    parser.add_argument(
        "demos",
        nargs="*",
        default=[],
        help="Demo(s) to run (default: all)",
    )
    parser.add_argument(
        "--ssh-user",
        default="root",
        help="SSH user for the server (default: root)",
    )
    parser.add_argument(
        "--admin-user",
        default="admin",
        help="Admin username to create (default: admin)",
    )
    parser.add_argument(
        "--admin-email",
        default="admin@example.com",
        help="Admin email (default: admin@example.com)",
    )
    parser.add_argument(
        "--admin-password",
        help="Admin password (default: randomly generated)",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        dest="use_local_code",
        help="Use local code via rsync instead of git/wheel",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Skip the Hop3 installation phase",
    )
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Don't destroy demo apps at the end",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=0.5,
        help="Pause between steps in seconds (default: 0.5)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Discover available demos
    available_demos = discover_demos()
    if not available_demos:
        print_error("No demos found in demos/ directory")
        return 1

    # Determine which demos to run
    demos_to_run = args.demos if args.demos else available_demos

    # Validate demo names
    for demo in demos_to_run:
        if demo not in available_demos:
            print_error(f"Unknown demo: '{demo}'")
            print_info(f"Available demos: {', '.join(available_demos)}")
            return 1

    # Generate password if not provided
    admin_password = args.admin_password or secrets.token_urlsafe(16)

    # Create context
    ctx = DemoContext(
        server_ip=args.server_ip,
        ssh_user=args.ssh_user,
        admin_user=args.admin_user,
        admin_email=args.admin_email,
        admin_password=admin_password,
        pause_between_steps=args.pause,
        skip_install=args.skip_install,
        no_cleanup=args.no_cleanup,
        use_local_code=args.use_local_code,
        verbose=args.verbose,
    )

    # Print banner and config
    print_banner()
    print_config(ctx, demos_to_run)

    try:
        # Phase 1: Prerequisites
        from lib.server import (
            check_hop3_installed,
            check_ubuntu_version,
            install_hop3,
            update_hop3_server,
            verify_ssh_access,
        )

        print_header("Phase 1: Prerequisites")

        verify_ssh_access(ctx)
        pause(ctx.pause_between_steps)

        check_ubuntu_version(ctx)
        pause(ctx.pause_between_steps)

        hop3_installed = check_hop3_installed(ctx)

        if not hop3_installed and not ctx.skip_install:
            install_hop3(ctx)
        elif hop3_installed:
            # Update to latest code
            update_hop3_server(ctx)
        elif ctx.skip_install:
            print_error("Hop3 is not installed and --skip-install was specified")
            return 1

        pause(ctx.pause_between_steps)

        # Phase 2: Configure CLI
        configure_cli(ctx)
        pause(ctx.pause_between_steps)

        # Phase 3: Run demos
        results = {}
        for demo_name in demos_to_run:
            success = run_demo(ctx, demo_name)
            results[demo_name] = success
            pause(ctx.pause_between_steps)

        # Summary
        print_header("Demo Summary")
        all_passed = all(results.values())

        for demo_name, passed in results.items():
            status = (
                f"{Colors.GREEN}PASS{Colors.RESET}"
                if passed
                else f"{Colors.RED}FAIL{Colors.RESET}"
            )
            print(f"  [{status}] {demo_name}")

        print()
        if all_passed:
            print_success("All demos completed successfully!")
            if ctx.no_cleanup:
                print()
                print("  Admin credentials:")
                print(f"    Username: {ctx.admin_user}")
                print(f"    Password: {ctx.admin_password}")
        else:
            print_error("Some demos failed")
            return 1

        return 0

    except KeyboardInterrupt:
        print()
        print_error("Demo interrupted by user")
        return 130


if __name__ == "__main__":
    sys.exit(main())
