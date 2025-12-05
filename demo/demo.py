#!/usr/bin/env python3
# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Hop3 Demo Script.

This script automates the complete Hop3 installation and quickstart workflow
on a blank Ubuntu server. Designed for generating screencasts with clear
on-screen messages.

Usage:
    python demo.py <server_ip> [options]

Examples:
    python demo.py 46.62.169.221
    python demo.py 46.62.169.221 --skip-install
    python demo.py 46.62.169.221 --no-cleanup
"""

from __future__ import annotations

import argparse
import os
import secrets
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# =============================================================================
# Configuration
# =============================================================================

HOP3_REPO = "https://github.com/abilian/hop3.git"
HOP3_BRANCH = "devel"
DEMO_APP_DIR = Path(__file__).parent / "hello-hop3"


# =============================================================================
# Terminal Output Helpers
# =============================================================================


class Colors:
    """ANSI color codes for terminal output."""

    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def print_header(title: str) -> None:
    """Print a prominent section header."""
    width = 68
    border = "═" * width
    print()
    print(f"{Colors.CYAN}{Colors.BOLD}╔{border}╗{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}║  {title:<{width - 2}}║{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}╚{border}╝{Colors.RESET}")
    print()


def print_step(message: str) -> None:
    """Print a step description."""
    print(f"{Colors.YELLOW}→{Colors.RESET} {message}")


def print_command(cmd: str) -> None:
    """Print a command that will be executed."""
    print()
    print(f"  {Colors.DIM}${Colors.RESET} {Colors.BOLD}{cmd}{Colors.RESET}")
    print()


def print_success(message: str) -> None:
    """Print a success message."""
    print(f"{Colors.GREEN}✓{Colors.RESET} {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    print(f"{Colors.RED}✗{Colors.RESET} {message}")


def print_info(message: str) -> None:
    """Print an informational message."""
    print(f"  {Colors.DIM}{message}{Colors.RESET}")


def pause(seconds: float = 1.0) -> None:
    """Pause for screencast narration."""
    time.sleep(seconds)


# =============================================================================
# Command Execution
# =============================================================================


@dataclass
class DemoContext:
    """Context for the demo execution."""

    server_ip: str
    admin_user: str
    admin_email: str
    admin_password: str
    app_hostname: str = "a1.hop.demo"
    ssh_user: str = "root"
    skip_install: bool = False
    no_cleanup: bool = False
    pause_between_steps: float = 0.5

    @property
    def ssh_target(self) -> str:
        return f"{self.ssh_user}@{self.server_ip}"

    @property
    def app_url(self) -> str:
        return f"https://{self.app_hostname}"


def run_local(cmd: str, *, show: bool = True, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command locally."""
    if show:
        print_command(cmd)
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        print_error(f"Command failed with exit code {result.returncode}")
        if result.stderr:
            print(f"  {Colors.RED}{result.stderr.strip()}{Colors.RESET}")
        sys.exit(1)
    return result


def run_ssh(ctx: DemoContext, cmd: str, *, show: bool = True, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command on the remote server via SSH."""
    ssh_cmd = f'ssh -o StrictHostKeyChecking=accept-new {ctx.ssh_target} "{cmd}"'
    if show:
        print_command(f"ssh {ctx.ssh_target} '{cmd}'")
    result = subprocess.run(ssh_cmd, shell=True, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        print_error(f"SSH command failed with exit code {result.returncode}")
        if result.stderr:
            print(f"  {Colors.RED}{result.stderr.strip()}{Colors.RESET}")
        sys.exit(1)
    return result


def run_hop3(cmd: str, *, show: bool = True, check: bool = True) -> subprocess.CompletedProcess:
    """Run a hop3 CLI command."""
    full_cmd = f"hop3 {cmd}"
    if show:
        print_command(full_cmd)
    result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True, check=False)
    if result.stdout:
        print(result.stdout)
    if check and result.returncode != 0:
        print_error(f"hop3 command failed with exit code {result.returncode}")
        if result.stderr:
            print(f"  {Colors.RED}{result.stderr.strip()}{Colors.RESET}")
        sys.exit(1)
    return result


# =============================================================================
# Phase 1: Server Installation
# =============================================================================


def verify_ssh_access(ctx: DemoContext) -> None:
    """Verify SSH access to the server."""
    print_step("Verifying SSH access to the server...")
    result = run_ssh(ctx, "echo 'SSH connection successful'", show=False, check=False)
    if result.returncode != 0:
        print_error(f"Cannot connect to {ctx.ssh_target}")
        print_info("Please ensure SSH key authentication is configured.")
        sys.exit(1)
    print_success(f"Connected to {ctx.server_ip}")


def check_ubuntu_version(ctx: DemoContext) -> None:
    """Check that the server is running a supported Ubuntu version."""
    print_step("Checking Ubuntu version...")
    result = run_ssh(ctx, "cat /etc/os-release | grep VERSION_ID", show=False)
    supported_versions = ["22.04", "24.04"]
    version_found = None
    for version in supported_versions:
        if version in result.stdout:
            version_found = version
            break
    if not version_found:
        print_error(f"This script requires Ubuntu {' or '.join(supported_versions)}")
        print_info(f"Found: {result.stdout.strip()}")
        sys.exit(1)
    print_success(f"Ubuntu {version_found} LTS detected")


def install_hop3_on_server(ctx: DemoContext) -> None:
    """Install Hop3 on the remote server."""
    print_header("PHASE 1: Installing Hop3 on the Server")

    verify_ssh_access(ctx)
    pause(ctx.pause_between_steps)

    check_ubuntu_version(ctx)
    pause(ctx.pause_between_steps)

    # Step 1: Update system packages
    print_step("Updating system packages...")
    run_ssh(ctx, "apt-get update -qq")
    print_success("System packages updated")
    pause(ctx.pause_between_steps)

    # Step 2: Build packages locally and run pyinfra to remote
    print_step("Building Hop3 packages locally...")

    # Get the local hop3 repo path
    hop3_repo = Path(__file__).parent.parent
    if not (hop3_repo / "installer" / "install-hop.py").exists():
        print_error("Cannot find Hop3 repository. Run this script from the hop3 directory.")
        sys.exit(1)

    # Build packages locally
    run_local(f"cd {hop3_repo} && uv build packages/hop3-server", show=False)
    run_local(f"cd {hop3_repo} && uv build packages/hop3-cli", show=False)
    print_success("Hop3 packages built locally")
    pause(ctx.pause_between_steps)

    # Step 3: Run the installer from local to remote
    print_step("Running Hop3 installer (this may take a few minutes)...")
    run_local(
        f"cd {hop3_repo} && uv run pyinfra -y --user root {ctx.server_ip} installer/install-hop.py",
    )
    print_success("Hop3 installation completed")
    pause(ctx.pause_between_steps)

    # Step 4: Install uwsgi (not included in hop3-server package)
    print_step("Installing uwsgi...")
    run_ssh(ctx, "/home/hop3/venv/bin/pip install uwsgi -q")
    run_ssh(ctx, "systemctl daemon-reload && systemctl restart uwsgi-hop3")
    print_success("uwsgi installed and running")
    pause(ctx.pause_between_steps)

    # Step 5: Run hop-server setup
    print_step("Running hop-server setup...")
    run_ssh(ctx, "su - hop3 -c '/home/hop3/venv/bin/hop-server setup'")
    print_success("hop-server setup completed")
    pause(ctx.pause_between_steps)

    # Step 6: Restart hop3-server service
    print_step("Restarting hop3-server service...")
    run_ssh(ctx, "systemctl restart hop3-server")
    run_ssh(ctx, "systemctl status hop3-server --no-pager")
    print_success("hop3-server service restarted")


# =============================================================================
# Phase 2: CLI Configuration
# =============================================================================


def configure_cli(ctx: DemoContext) -> None:
    """Configure the local Hop3 CLI."""
    print_header("PHASE 2: Configuring Hop3 CLI")

    # Check if hop3 CLI is available
    print_step("Checking hop3 CLI availability...")
    result = run_local("which hop3", show=False, check=False)
    if result.returncode != 0:
        print_error("hop3 CLI not found. Please install it first.")
        print_info("Run: pip install hop3-cli")
        sys.exit(1)
    print_success("hop3 CLI found")
    pause(ctx.pause_between_steps)

    # Create admin user via SSH (or login if user already exists)
    print_step(f"Setting up admin user '{ctx.admin_user}'...")
    print_info("This will connect via SSH and create/login the admin account.")

    # Use non-interactive mode for automation
    init_cmd = (
        f"echo '{ctx.admin_password}' | hop3 init "
        f"--ssh {ctx.ssh_target} "
        f"--username {ctx.admin_user} "
        f"--email {ctx.admin_email} "
        f"--server http://{ctx.server_ip}:8000 "
        f"--password-stdin --yes"
    )
    print_command(f"hop3 init --ssh {ctx.ssh_target} --username {ctx.admin_user} --email {ctx.admin_email}")

    result = subprocess.run(init_cmd, shell=True, capture_output=True, text=True, check=False)
    if result.stdout:
        print(result.stdout)

    if result.returncode != 0:
        # Check if user already exists - try login instead
        if "already exists" in result.stderr:
            print_info("Admin user already exists, attempting login...")
            login_cmd = (
                f"echo '{ctx.admin_password}' | hop3 login "
                f"--ssh {ctx.ssh_target} "
                f"--username {ctx.admin_user} "
                f"--server http://{ctx.server_ip}:8000 "
                f"--password-stdin"
            )
            result = subprocess.run(login_cmd, shell=True, capture_output=True, text=True, check=False)
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


# =============================================================================
# Phase 3: Deploy Sample Application
# =============================================================================


def deploy_sample_app(ctx: DemoContext) -> None:
    """Deploy the hello-hop3 sample application."""
    print_header("PHASE 3: Deploying Sample Application")

    # Show the app structure
    print_step("Sample application structure:")
    print()
    print(f"  {Colors.CYAN}hello-hop3/{Colors.RESET}")
    print(f"  ├── {Colors.GREEN}app.py{Colors.RESET}           - Flask application")
    print(f"  ├── {Colors.GREEN}requirements.txt{Colors.RESET} - Python dependencies")
    print(f"  └── {Colors.GREEN}hop3.toml{Colors.RESET}        - Hop3 configuration")
    print()
    pause(ctx.pause_between_steps)

    # Show hop3.toml content
    print_step("Hop3 configuration (hop3.toml):")
    hop3_toml = DEMO_APP_DIR / "hop3.toml"
    if hop3_toml.exists():
        print()
        content = hop3_toml.read_text()
        for line in content.split("\n")[:15]:  # Show first 15 lines
            print(f"  {Colors.DIM}{line}{Colors.RESET}")
        print()
    pause(ctx.pause_between_steps)

    # Deploy the application
    print_step("Deploying hello-hop3 application...")
    original_dir = os.getcwd()
    try:
        os.chdir(DEMO_APP_DIR)
        run_hop3("deploy hello-hop3")
    finally:
        os.chdir(original_dir)
    print_success("Application deployed")
    pause(ctx.pause_between_steps)

    # Wait for app to start
    print_step("Waiting for application to start...")
    time.sleep(3)

    # Verify deployment
    print_step("Checking application status...")
    run_hop3("app:status hello-hop3")
    print_success("Application is running")


# =============================================================================
# Phase 4: Application Management Demo
# =============================================================================


def demo_app_management(ctx: DemoContext) -> None:
    """Demonstrate application management commands."""
    print_header("PHASE 4: Application Management")

    # List all apps
    print_step("Listing all deployed applications...")
    run_hop3("apps")
    pause(ctx.pause_between_steps)

    # Check detailed status
    print_step("Checking detailed application status...")
    run_hop3("app:status hello-hop3")
    pause(ctx.pause_between_steps)

    # Test the application via HTTP
    print_step("Testing the application via HTTP...")
    test_url = f"http://{ctx.server_ip}:8000"
    print_info("Note: In production, you'd access via hostname.")
    print_info(f"For this demo, we'll use the server IP: {test_url}")

    # Get the app port from status and test it
    result = run_hop3("app:ping hello-hop3", check=False)
    pause(ctx.pause_between_steps)

    # Set environment variables
    print_step("Setting environment variables...")
    run_hop3("config:set hello-hop3 DEBUG=true LOG_LEVEL=info")
    pause(ctx.pause_between_steps)

    # Show environment variables
    print_step("Viewing environment variables...")
    run_hop3("config:show hello-hop3")
    pause(ctx.pause_between_steps)

    # Restart app to apply changes
    print_step("Restarting application to apply changes...")
    run_hop3("app:restart hello-hop3")

    # Wait for restart
    time.sleep(2)
    print_success("Application restarted")
    pause(ctx.pause_between_steps)

    # Check status again
    print_step("Verifying application status after restart...")
    run_hop3("app:status hello-hop3")


# =============================================================================
# Phase 5: Cleanup
# =============================================================================


def cleanup(ctx: DemoContext) -> None:
    """Clean up the demo application."""
    print_header("PHASE 5: Cleanup")

    print_step("Destroying the hello-hop3 application...")
    print_info("Using -y flag to skip confirmation prompt")
    run_hop3("app:destroy hello-hop3 -y")
    print_success("Application destroyed")
    pause(ctx.pause_between_steps)

    # Verify cleanup
    print_step("Verifying cleanup - listing applications...")
    run_hop3("apps")
    print_success("Cleanup complete")


# =============================================================================
# Main Entry Point
# =============================================================================


def print_banner() -> None:
    """Print the demo banner."""
    banner = """
    ╦ ╦╔═╗╔═╗┌─┐  ╔╦╗┌─┐┌┬┐┌─┐
    ╠═╣║ ║╠═╝  ─┤   ║║├┤ ││││ │
    ╩ ╩╚═╝╩  └─┘  ═╩╝└─┘┴ ┴└─┘

    Hop3 Installation & Quickstart Demo
    ====================================
    """
    print(f"{Colors.CYAN}{Colors.BOLD}{banner}{Colors.RESET}")


def print_summary(ctx: DemoContext) -> None:
    """Print a summary of what the demo will do."""
    print(f"{Colors.BOLD}Demo Configuration:{Colors.RESET}")
    print(f"  Server IP:     {ctx.server_ip}")
    print(f"  SSH Target:    {ctx.ssh_target}")
    print(f"  Admin User:    {ctx.admin_user}")
    print(f"  Admin Email:   {ctx.admin_email}")
    print(f"  Skip Install:  {ctx.skip_install}")
    print(f"  No Cleanup:    {ctx.no_cleanup}")
    print()


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Hop3 Installation & Quickstart Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python demo.py 46.62.169.221
  python demo.py 46.62.169.221 --skip-install
  python demo.py 46.62.169.221 --admin-user myuser --admin-email me@example.com
        """,
    )
    parser.add_argument("server_ip", help="IP address of the target server")
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
        "--skip-install",
        action="store_true",
        help="Skip the installation phase (assume Hop3 is already installed)",
    )
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Don't destroy the demo app at the end",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=0.5,
        help="Pause between steps in seconds (default: 0.5)",
    )
    return parser.parse_args()


def main() -> None:
    """Main entry point."""
    args = parse_args()

    # Generate password if not provided
    admin_password = args.admin_password or secrets.token_urlsafe(16)

    ctx = DemoContext(
        server_ip=args.server_ip,
        ssh_user=args.ssh_user,
        admin_user=args.admin_user,
        admin_email=args.admin_email,
        admin_password=admin_password,
        skip_install=args.skip_install,
        no_cleanup=args.no_cleanup,
        pause_between_steps=args.pause,
    )

    print_banner()
    print_summary(ctx)

    # Confirm before proceeding
    if not args.skip_install:
        print(f"{Colors.YELLOW}This will install Hop3 on {ctx.server_ip}.{Colors.RESET}")
        print(f"{Colors.YELLOW}The server should be a fresh Ubuntu 22.04 installation.{Colors.RESET}")
        print()

    try:
        # Phase 1: Installation
        if not ctx.skip_install:
            install_hop3_on_server(ctx)
        else:
            print_info("Skipping installation phase (--skip-install)")

        # Phase 2: CLI Configuration
        configure_cli(ctx)

        # Phase 3: Deploy Sample App
        deploy_sample_app(ctx)

        # Phase 4: App Management Demo
        demo_app_management(ctx)

        # Phase 5: Cleanup
        if not ctx.no_cleanup:
            cleanup(ctx)
        else:
            print_info("Skipping cleanup (--no-cleanup)")

        # Final summary
        print_header("Demo Complete!")
        print_success("The Hop3 demo has finished successfully.")
        print()
        if ctx.no_cleanup:
            print(f"  Your application is running at: http://{ctx.server_ip}")
            print("  Admin credentials:")
            print(f"    Username: {ctx.admin_user}")
            print(f"    Password: {ctx.admin_password}")
        print()
        print("  For more information, visit: https://hop3.cloud")
        print()

    except KeyboardInterrupt:
        print()
        print_error("Demo interrupted by user")
        sys.exit(1)


if __name__ == "__main__":
    main()
