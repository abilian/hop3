#!/usr/bin/env python3
# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Hop3 Demo 2 - Docker Deployment.

This script demonstrates deploying a Docker-based application with Hop3.
It assumes Hop3 is already installed (use demo1 first for fresh servers).

Usage:
    python demo.py <server_ip> [options]

Examples:
    python demo.py 46.62.169.221
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

APP_NAME = "hello-docker"
DEMO_APP_DIR = Path(__file__).parent / "hello-docker"


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
    app_hostname: str = "a2.hop.demo"
    ssh_user: str = "root"
    no_cleanup: bool = False
    pause_between_steps: float = 0.5

    @property
    def ssh_target(self) -> str:
        return f"{self.ssh_user}@{self.server_ip}"

    @property
    def app_url(self) -> str:
        return f"https://{self.app_hostname}"


def run_local(
    cmd: str, *, show: bool = True, check: bool = True
) -> subprocess.CompletedProcess:
    """Run a command locally."""
    if show:
        print_command(cmd)
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, check=False
    )
    if check and result.returncode != 0:
        print_error(f"Command failed with exit code {result.returncode}")
        if result.stderr:
            print(f"  {Colors.RED}{result.stderr.strip()}{Colors.RESET}")
        sys.exit(1)
    return result


def run_ssh(
    ctx: DemoContext, cmd: str, *, show: bool = True, check: bool = True
) -> subprocess.CompletedProcess:
    """Run a command on the remote server via SSH."""
    ssh_cmd = f'ssh -o StrictHostKeyChecking=accept-new {ctx.ssh_target} "{cmd}"'
    if show:
        print_command(f"ssh {ctx.ssh_target} '{cmd}'")
    result = subprocess.run(
        ssh_cmd, shell=True, capture_output=True, text=True, check=False
    )
    if check and result.returncode != 0:
        print_error(f"SSH command failed with exit code {result.returncode}")
        if result.stderr:
            print(f"  {Colors.RED}{result.stderr.strip()}{Colors.RESET}")
        sys.exit(1)
    return result


def run_hop3(
    cmd: str, *, show: bool = True, check: bool = True
) -> subprocess.CompletedProcess:
    """Run a hop3 CLI command."""
    full_cmd = f"hop3 {cmd}"
    if show:
        print_command(full_cmd)
    result = subprocess.run(
        full_cmd, shell=True, capture_output=True, text=True, check=False
    )
    if result.stdout:
        print(result.stdout)
    if check and result.returncode != 0:
        print_error(f"hop3 command failed with exit code {result.returncode}")
        if result.stderr:
            print(f"  {Colors.RED}{result.stderr.strip()}{Colors.RESET}")
        sys.exit(1)
    return result


# =============================================================================
# Phase 1: Prerequisites Check
# =============================================================================


def update_hop3_server(ctx: DemoContext) -> None:
    """Update hop3-server on the remote server from local build."""
    print_step("Updating hop3-server to latest version...")

    # Get the local hop3 repo path
    hop3_repo = Path(__file__).parent.parent.parent
    server_pkg = hop3_repo / "packages" / "hop3-server"

    if not server_pkg.exists():
        print_error("Cannot find hop3-server package directory.")
        sys.exit(1)

    # Build the package locally
    print_info("Building hop3-server package locally...")
    result = run_local(f"cd {hop3_repo} && uv build packages/hop3-server", show=False, check=False)
    if result.returncode != 0:
        print_error("Failed to build hop3-server package.")
        sys.exit(1)

    # Find the built wheel
    dist_dir = hop3_repo / "packages" / "hop3-server" / "dist"
    wheels = list(dist_dir.glob("hop3_server-*.whl"))
    if not wheels:
        print_error("No wheel file found after build.")
        sys.exit(1)
    wheel_path = max(wheels, key=lambda p: p.stat().st_mtime)  # Latest wheel

    # Copy wheel to server
    print_info(f"Copying {wheel_path.name} to server...")
    run_local(
        f"scp -o StrictHostKeyChecking=accept-new {wheel_path} {ctx.ssh_target}:/tmp/",
        show=False,
    )

    # Install the wheel on server
    print_info("Installing hop3-server on server...")
    run_ssh(
        ctx,
        f"/home/hop3/venv/bin/pip install --upgrade /tmp/{wheel_path.name}",
        show=False,
    )

    # Restart hop3-server to load new code
    print_info("Restarting hop3-server...")
    run_ssh(ctx, "systemctl restart hop3-server", show=False)
    time.sleep(2)

    print_success("hop3-server updated")


def verify_prerequisites(ctx: DemoContext) -> None:
    """Verify prerequisites for Docker deployment."""
    print_header("PHASE 1: Checking Prerequisites")

    # Verify SSH access
    print_step("Verifying SSH access to the server...")
    result = run_ssh(ctx, "echo 'SSH connection successful'", show=False, check=False)
    if result.returncode != 0:
        print_error(f"Cannot connect to {ctx.ssh_target}")
        print_info("Please ensure SSH key authentication is configured.")
        sys.exit(1)
    print_success(f"Connected to {ctx.server_ip}")
    pause(ctx.pause_between_steps)

    # Check if Hop3 is installed
    print_step("Checking if Hop3 is installed...")
    result = run_ssh(ctx, "test -f /home/hop3/venv/bin/hop-server", show=False, check=False)
    if result.returncode != 0:
        print_error("Hop3 is not installed on this server.")
        print_info("Please run demo1 first to install Hop3.")
        sys.exit(1)
    print_success("Hop3 is installed")
    pause(ctx.pause_between_steps)

    # Update hop3-server to latest version from local build
    update_hop3_server(ctx)
    pause(ctx.pause_between_steps)

    # Check if Docker is installed
    print_step("Checking if Docker is installed...")
    result = run_ssh(ctx, "which docker", show=False, check=False)
    if result.returncode != 0:
        print_info("Docker is not installed. Installing docker.io package...")
        run_ssh(ctx, "apt-get update -qq && apt-get install -y -qq docker.io")
        run_ssh(ctx, "systemctl enable docker && systemctl start docker")
        print_success("Docker installed and started")
    else:
        print_success("Docker is available")
    pause(ctx.pause_between_steps)

    # Ensure hop3 user is in docker group
    print_step("Ensuring hop3 user is in docker group...")
    result = run_ssh(ctx, "groups hop3 | grep -q docker", show=False, check=False)
    if result.returncode != 0:
        print_info("Adding hop3 user to docker group...")
        run_ssh(ctx, "usermod -aG docker hop3")
    else:
        print_info("hop3 user is already in docker group")

    # Always restart hop3-server to ensure it has docker group access
    # (the running process may have been started before group membership)
    print_step("Restarting hop3-server to ensure Docker access...")
    run_ssh(ctx, "systemctl restart hop3-server")
    time.sleep(3)  # Give the service time to restart
    print_success("hop3-server restarted")

    # Verify hop3-server can access Docker
    print_step("Verifying hop3-server can access Docker...")
    # Test by running docker through hop3-server's environment
    result = run_ssh(ctx, "su - hop3 -c 'docker ps'", show=False, check=False)
    if result.returncode != 0:
        print_error("hop3 user still cannot access Docker.")
        print_info("Check: groups hop3 and systemctl status hop3-server")
        sys.exit(1)
    print_success("Docker access verified")
    pause(ctx.pause_between_steps)

    # Check hop3 CLI
    print_step("Checking hop3 CLI availability...")
    result = run_local("which hop3", show=False, check=False)
    if result.returncode != 0:
        print_error("hop3 CLI not found. Please install it first.")
        print_info("Run: pip install hop3-cli")
        sys.exit(1)
    print_success("hop3 CLI found")


# =============================================================================
# Phase 2: CLI Configuration
# =============================================================================


def configure_cli(ctx: DemoContext) -> None:
    """Configure the local Hop3 CLI."""
    print_header("PHASE 2: Configuring Hop3 CLI")

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
    print_command(
        f"hop3 init --ssh {ctx.ssh_target} --username {ctx.admin_user} --email {ctx.admin_email}"
    )

    result = subprocess.run(
        init_cmd, shell=True, capture_output=True, text=True, check=False
    )
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


# =============================================================================
# Phase 3: Deploy Docker Application
# =============================================================================


def deploy_docker_app(ctx: DemoContext) -> None:
    """Deploy the Docker-based hello-docker application."""
    print_header("PHASE 3: Deploying Docker Application")

    # Show the app structure
    print_step("Docker application structure:")
    print()
    print(f"  {Colors.CYAN}hello-docker/{Colors.RESET}")
    print(f"  ├── {Colors.GREEN}app.py{Colors.RESET}             - Flask application")
    print(f"  ├── {Colors.GREEN}requirements.txt{Colors.RESET}   - Python dependencies")
    print(f"  ├── {Colors.BLUE}Dockerfile{Colors.RESET}          - Container image definition")
    print(f"  └── {Colors.GREEN}hop3.toml{Colors.RESET}          - Hop3 configuration")
    print()
    print_info("Note: Hop3 generates docker-compose.yml automatically from the Dockerfile.")
    print()
    pause(ctx.pause_between_steps)

    # Show Dockerfile content
    print_step("Dockerfile (container image definition):")
    dockerfile = DEMO_APP_DIR / "Dockerfile"
    if dockerfile.exists():
        print()
        content = dockerfile.read_text()
        for line in content.split("\n"):
            print(f"  {Colors.DIM}{line}{Colors.RESET}")
        print()
    pause(ctx.pause_between_steps)

    # Show hop3.toml content
    print_step("Hop3 configuration (hop3.toml):")
    hop3_toml = DEMO_APP_DIR / "hop3.toml"
    if hop3_toml.exists():
        print()
        content = hop3_toml.read_text()
        for line in content.split("\n"):
            print(f"  {Colors.DIM}{line}{Colors.RESET}")
        print()
    pause(ctx.pause_between_steps)

    # Deploy the application (first time creates the app and builds Docker image)
    print_step(f"Deploying {APP_NAME} application...")
    print_info("This will build the Docker image and start the container.")
    original_dir = os.getcwd()
    try:
        os.chdir(DEMO_APP_DIR)
        run_hop3(f"deploy {APP_NAME}")
    finally:
        os.chdir(original_dir)
    print_success("Application deployed")
    pause(ctx.pause_between_steps)

    # Set the hostname for the app (now that it exists)
    print_step(f"Configuring hostname: {ctx.app_hostname}")
    run_hop3(f"config:set {APP_NAME} HOST_NAME={ctx.app_hostname}")
    print_success(f"Hostname set to {ctx.app_hostname}")
    pause(ctx.pause_between_steps)

    # Redeploy to regenerate nginx config with the hostname
    print_step("Redeploying to apply hostname configuration...")
    try:
        os.chdir(DEMO_APP_DIR)
        run_hop3(f"deploy {APP_NAME}")
    finally:
        os.chdir(original_dir)
    print_success("Application redeployed with hostname")
    pause(ctx.pause_between_steps)

    # Wait for container to start
    print_step("Waiting for container to start...")
    time.sleep(5)

    # Verify deployment
    print_step("Checking application status...")
    run_hop3(f"app:status {APP_NAME}")
    print_success("Docker container is running")


# =============================================================================
# Phase 4: Application Management Demo
# =============================================================================


def demo_app_management(ctx: DemoContext) -> None:
    """Demonstrate Docker application management commands."""
    print_header("PHASE 4: Docker Application Management")

    # List all apps
    print_step("Listing all deployed applications...")
    run_hop3("apps")
    pause(ctx.pause_between_steps)

    # Check detailed status
    print_step("Checking detailed application status...")
    run_hop3(f"app:status {APP_NAME}")
    pause(ctx.pause_between_steps)

    # Show Docker containers on server
    print_step("Viewing Docker containers on server...")
    run_ssh(ctx, "su - hop3 -c 'docker ps --filter name=hello-docker'")
    pause(ctx.pause_between_steps)

    # Test the application via HTTPS with virtual host
    print_step(f"Testing the application via HTTPS at {ctx.app_url}...")
    print_info("Using curl with -k flag to accept self-signed certificate.")

    # First, use hop3's built-in ping (internal check)
    run_hop3(f"app:ping {APP_NAME}", check=False)
    pause(ctx.pause_between_steps)

    # Now test via the actual public URL with curl
    print_step(f"Verifying external access via {ctx.app_url}...")
    curl_cmd = f"curl -sk {ctx.app_url}/"
    print_command(curl_cmd)
    result = subprocess.run(
        curl_cmd, shell=True, capture_output=True, text=True, check=False
    )

    # Check that we got our app's response, not nginx default page
    expected_content = "Hello from Docker"
    if result.returncode == 0 and expected_content in result.stdout:
        print(f"  {Colors.GREEN}Response:{Colors.RESET}")
        print(f"  {result.stdout.strip()}")
        print()
        print_success(f"Docker application accessible at {ctx.app_url}")
    else:
        print_error(f"Failed to access application at {ctx.app_url}")
        print()
        if result.stdout:
            print(f"  {Colors.YELLOW}Got response:{Colors.RESET}")
            print(f"  {result.stdout[:200].strip()}")
            print()
        if result.stderr:
            print(f"  {Colors.RED}Error: {result.stderr.strip()}{Colors.RESET}")
        print_error(
            f"Expected response containing '{expected_content}' but got nginx default page or error."
        )
        print_info("This usually means HOST_NAME was not applied correctly to nginx config.")
        sys.exit(1)
    pause(ctx.pause_between_steps)

    # Test the /info endpoint
    print_step("Testing the /info endpoint...")
    curl_cmd = f"curl -sk {ctx.app_url}/info"
    print_command(curl_cmd)
    result = subprocess.run(
        curl_cmd, shell=True, capture_output=True, text=True, check=False
    )
    if result.returncode == 0:
        print(f"  {Colors.GREEN}Container info:{Colors.RESET}")
        print(f"  {result.stdout.strip()}")
        print()
    pause(ctx.pause_between_steps)

    # Set environment variables
    print_step("Setting environment variables...")
    run_hop3(f"config:set {APP_NAME} FLASK_ENV=development DEBUG=true")
    pause(ctx.pause_between_steps)

    # Show environment variables
    print_step("Viewing environment variables...")
    run_hop3(f"config:show {APP_NAME}")
    pause(ctx.pause_between_steps)

    # Restart container to apply changes
    print_step("Restarting container to apply changes...")
    run_hop3(f"app:restart {APP_NAME}")

    # Wait for restart
    time.sleep(3)
    print_success("Container restarted")
    pause(ctx.pause_between_steps)

    # Check status again
    print_step("Verifying application status after restart...")
    run_hop3(f"app:status {APP_NAME}")


# =============================================================================
# Phase 5: Cleanup
# =============================================================================


def cleanup(ctx: DemoContext) -> None:
    """Clean up the demo application."""
    print_header("PHASE 5: Cleanup")

    print_step(f"Destroying the {APP_NAME} application...")
    print_info("This will stop and remove the Docker container.")
    run_hop3(f"app:destroy {APP_NAME} -y")
    print_success("Application destroyed")
    pause(ctx.pause_between_steps)

    # Verify cleanup
    print_step("Verifying cleanup - listing applications...")
    run_hop3("apps")
    pause(ctx.pause_between_steps)

    # Show Docker containers
    print_step("Verifying Docker containers removed...")
    run_ssh(ctx, "su - hop3 -c 'docker ps -a --filter name=hello-docker'", check=False)
    print_success("Cleanup complete")


# =============================================================================
# Main Entry Point
# =============================================================================


def print_banner() -> None:
    """Print the demo banner."""
    banner = """
    ╦ ╦╔═╗╔═╗┌─┐  ╔╦╗┌─┐┌┬┐┌─┐  ┌─┐
    ╠═╣║ ║╠═╝ ─┤   ║║├┤ ││││ │  ┌─┘
    ╩ ╩╚═╝╩  └─┘  ═╩╝└─┘┴ ┴└─┘  └─┘

    Docker Deployment Demo
    ======================
    """
    print(f"{Colors.CYAN}{Colors.BOLD}{banner}{Colors.RESET}")


def print_summary(ctx: DemoContext) -> None:
    """Print a summary of what the demo will do."""
    print(f"{Colors.BOLD}Demo Configuration:{Colors.RESET}")
    print(f"  Server IP:     {ctx.server_ip}")
    print(f"  SSH Target:    {ctx.ssh_target}")
    print(f"  Admin User:    {ctx.admin_user}")
    print(f"  App Name:      {APP_NAME}")
    print(f"  App Hostname:  {ctx.app_hostname}")
    print(f"  App URL:       {ctx.app_url}")
    print(f"  No Cleanup:    {ctx.no_cleanup}")
    print()
    print(f"{Colors.BLUE}This demo showcases Docker-based deployment with Hop3:{Colors.RESET}")
    print("  - Building Docker images from Dockerfile")
    print("  - Deploying containers with Docker Compose")
    print("  - Routing traffic through nginx proxy")
    print()


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Hop3 Docker Deployment Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python demo.py 46.62.169.221
  python demo.py 46.62.169.221 --no-cleanup
  python demo.py 46.62.169.221 --app-hostname myapp.example.com
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
        help="Admin username (default: admin)",
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
        "--app-hostname",
        default="a2.hop.demo",
        help="Hostname for the demo app (default: a2.hop.demo)",
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
        app_hostname=args.app_hostname,
        no_cleanup=args.no_cleanup,
        pause_between_steps=args.pause,
    )

    print_banner()
    print_summary(ctx)

    try:
        # Phase 1: Prerequisites Check
        verify_prerequisites(ctx)

        # Phase 2: CLI Configuration
        configure_cli(ctx)

        # Phase 3: Deploy Docker App
        deploy_docker_app(ctx)

        # Phase 4: App Management Demo
        demo_app_management(ctx)

        # Phase 5: Cleanup
        if not ctx.no_cleanup:
            cleanup(ctx)
        else:
            print_info("Skipping cleanup (--no-cleanup)")

        # Final summary
        print_header("Demo Complete!")
        print_success("The Docker deployment demo has finished successfully.")
        print()
        if ctx.no_cleanup:
            print(f"  Your Docker application is running at: {ctx.app_url}")
            print(f"  Test it with: curl -sk {ctx.app_url}/")
            print(f"  Container info: curl -sk {ctx.app_url}/info")
            print()
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
