#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Abilian SAS
"""Deploy Hop3 to a remote server.

This is a developer tool for deploying Hop3 to a test/development server
without having to SSH in and type commands manually.

Usage:
    python scripts/deploy-server.py --host HOST [options]
    python scripts/deploy-server.py --help

Examples:
    python scripts/deploy-server.py --host 192.168.1.100                    # Fresh install
    python scripts/deploy-server.py --host 192.168.1.100 --local            # Use local code
    python scripts/deploy-server.py --host 192.168.1.100 --skip-install     # Update only
    python scripts/deploy-server.py --host 192.168.1.100 --clean-before     # Clean reinstall
"""

from __future__ import annotations

import argparse
import secrets
import socket
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path


# ANSI color codes
class Colors:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    CYAN = "\033[0;36m"
    DIM = "\033[2m"
    NC = "\033[0m"  # No Color


def print_header(text: str) -> None:
    print(f"\n{Colors.BLUE}=== {text} ==={Colors.NC}")


def print_step(text: str) -> None:
    print(f"  {Colors.CYAN}>{Colors.NC} {text}")


def print_success(text: str) -> None:
    print(f"  {Colors.GREEN}[OK]{Colors.NC} {text}")


def print_error(text: str) -> None:
    print(f"  {Colors.RED}[ERROR]{Colors.NC} {text}", file=sys.stderr)


def print_info(text: str) -> None:
    print(f"  {Colors.DIM}{text}{Colors.NC}")


def print_warning(text: str) -> None:
    print(f"  {Colors.YELLOW}[WARN]{Colors.NC} {text}")


class CommandError(Exception):
    """Raised when a command fails."""

    def __init__(self, message: str, returncode: int = 1):
        super().__init__(message)
        self.returncode = returncode


@dataclass
class DeployContext:
    """Context for deployment."""

    # Server connection
    server_ip: str
    ssh_user: str = "root"
    admin_domain: str | None = None

    # Admin credentials
    admin_user: str = "admin"
    admin_email: str = "admin@example.com"
    admin_password: str = ""

    # Deployment settings
    skip_install: bool = False
    use_local_code: bool = False
    clean_before: bool = False
    verbose: bool = False
    branch: str = "devel"
    with_features: list[str] = field(default_factory=list)

    # Paths
    project_root: Path = field(default_factory=lambda: Path(__file__).parent.parent)

    @property
    def ssh_target(self) -> str:
        return f"{self.ssh_user}@{self.server_ip}"

    @property
    def installer_path(self) -> Path:
        return self.project_root / "installer" / "install-server.py"

    @property
    def packages_path(self) -> Path:
        return self.project_root / "packages"

    @property
    def dist_path(self) -> Path:
        return self.project_root / "dist"


def run_local(
    cmd: str,
    *,
    show: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """Run a command locally."""
    if show:
        print_info(f"$ {cmd}")
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, check=False
    )
    if check and result.returncode != 0:
        print_error(f"Command failed with exit code {result.returncode}")
        if result.stderr:
            print(f"  {Colors.RED}{result.stderr.strip()}{Colors.NC}")
        raise CommandError(f"Command failed: {cmd}", result.returncode)
    return result


def run_ssh(
    ctx: DeployContext,
    cmd: str,
    *,
    show: bool = True,
    check: bool = True,
    show_full_output_on_error: bool = False,
) -> subprocess.CompletedProcess:
    """Run a command on the remote server via SSH."""
    ssh_cmd = f'ssh -o StrictHostKeyChecking=accept-new {ctx.ssh_target} "{cmd}"'
    if show:
        print_info(f"[ssh] {cmd}")
    result = subprocess.run(
        ssh_cmd, shell=True, capture_output=True, text=True, check=False
    )
    if check and result.returncode != 0:
        print_error(f"SSH command failed with exit code {result.returncode}")
        if show_full_output_on_error:
            # Show full output for debugging
            if result.stdout:
                print(f"\n{Colors.CYAN}--- STDOUT ---{Colors.NC}")
                print(result.stdout)
            if result.stderr:
                print(f"\n{Colors.RED}--- STDERR ---{Colors.NC}")
                print(result.stderr)
        else:
            # Show truncated output
            if result.stdout:
                print(f"  {result.stdout.strip()}")
            if result.stderr:
                print(f"  {Colors.RED}{result.stderr.strip()}{Colors.NC}")
        raise CommandError(f"SSH command failed: {cmd}", result.returncode)
    return result


def verify_ssh_access(ctx: DeployContext) -> None:
    """Verify SSH access to the server."""
    print_step("Verifying SSH access...")
    result = run_ssh(ctx, "echo 'SSH connection successful'", show=False, check=False)
    if result.returncode != 0:
        print_error(f"Cannot connect to {ctx.ssh_target}")
        print_info("Please ensure SSH key authentication is configured.")
        raise CommandError(f"Cannot connect to {ctx.ssh_target}")
    print_success(f"Connected to {ctx.server_ip}")


def check_ubuntu_version(ctx: DeployContext) -> str | None:
    """Check that the server is running a supported Ubuntu version."""
    print_step("Checking Ubuntu version...")
    result = run_ssh(ctx, "cat /etc/os-release | grep VERSION_ID", show=False)
    supported_versions = ["22.04", "24.04"]
    for version in supported_versions:
        if version in result.stdout:
            print_success(f"Ubuntu {version} LTS detected")
            return version
    print_error(f"Unsupported Ubuntu version: {result.stdout.strip()}")
    print_info(f"Supported versions: {', '.join(supported_versions)}")
    return None


def check_hop3_installed(ctx: DeployContext) -> bool:
    """Check if Hop3 is installed on the server."""
    print_step("Checking if Hop3 is installed...")
    result = run_ssh(
        ctx, "test -f /home/hop3/venv/bin/hop3-server", show=False, check=False
    )
    if result.returncode == 0:
        print_success("Hop3 is installed")
        return True
    print_info("Hop3 is not installed")
    return False


def clean_server(ctx: DeployContext) -> None:
    """Clean the server completely before deployment."""
    print_header("Cleaning server")

    print_step("Stopping hop3-server service...")
    run_ssh(ctx, "systemctl stop hop3-server 2>/dev/null || true", show=False, check=False)
    print_success("hop3-server stopped")

    print_step("Stopping Docker containers...")
    run_ssh(
        ctx,
        "docker ps -q | xargs -r docker stop 2>/dev/null || true",
        show=False,
        check=False,
    )
    run_ssh(
        ctx,
        "docker ps -aq | xargs -r docker rm 2>/dev/null || true",
        show=False,
        check=False,
    )
    print_success("Docker containers stopped")

    print_step("Removing nginx app configurations...")
    run_ssh(
        ctx,
        "rm -f /etc/nginx/sites-enabled/hop3-* 2>/dev/null || true",
        show=False,
        check=False,
    )
    run_ssh(
        ctx,
        "rm -f /etc/nginx/sites-available/hop3-* 2>/dev/null || true",
        show=False,
        check=False,
    )
    run_ssh(ctx, "systemctl reload nginx 2>/dev/null || true", show=False, check=False)
    print_success("Nginx configurations removed")

    print_step("Removing /home/hop3 directory...")
    run_ssh(ctx, "rm -rf /home/hop3", show=False, check=False)
    print_success("/home/hop3 removed")

    print_step("Recreating hop3 user home directory...")
    run_ssh(ctx, "mkdir -p /home/hop3 && chown hop3:hop3 /home/hop3", show=False, check=False)
    print_success("hop3 home directory recreated")


def sync_local_code(ctx: DeployContext) -> None:
    """Sync local hop3-server code to the server using rsync."""
    print_step("Syncing local hop3-server code to server...")

    server_pkg = ctx.packages_path / "hop3-server"
    if not server_pkg.exists():
        print_error(f"Cannot find hop3-server package at {server_pkg}")
        raise CommandError(f"Package not found: {server_pkg}")

    rsync_cmd = (
        f"rsync -avz --delete "
        f"--exclude='*.pyc' --exclude='__pycache__' --exclude='.git' "
        f"--exclude='*.egg-info' --exclude='.pytest_cache' --exclude='dist' "
        f"{server_pkg}/ {ctx.ssh_target}:/tmp/hop3-server/"
    )
    print_info(f"Syncing {server_pkg} to server...")
    result = run_local(rsync_cmd, show=ctx.verbose, check=False)
    if result.returncode != 0:
        print_error("Failed to sync code to server")
        raise CommandError(f"Failed to sync code (exit code {result.returncode})")

    # Fix permissions
    run_ssh(ctx, "chmod -R a+rX /tmp/hop3-server", show=False, check=False)
    print_success("Local code synced to server")


def install_hop3(ctx: DeployContext) -> None:
    """Install Hop3 on the server."""
    print_header("Installing Hop3")

    if not ctx.installer_path.exists():
        print_error(f"Cannot find installer at {ctx.installer_path}")
        raise CommandError(f"Installer not found: {ctx.installer_path}")

    # Copy installer to server
    print_step("Copying installer to server...")
    run_local(
        f"scp -o StrictHostKeyChecking=accept-new {ctx.installer_path} {ctx.ssh_target}:/tmp/install-server.py",
        show=ctx.verbose,
    )
    print_success("Installer copied")

    # Build installer command
    domain_arg = f" --domain {ctx.admin_domain}" if ctx.admin_domain else ""
    with_arg = f" --with {','.join(ctx.with_features)}" if ctx.with_features else " --with all"

    if ctx.use_local_code:
        sync_local_code(ctx)
        print_step("Running installer with local code...")
        run_ssh(
            ctx,
            f"python3 /tmp/install-server.py --local-path /tmp/hop3-server{domain_arg}{with_arg} --verbose",
            show_full_output_on_error=True,
        )
    else:
        print_step(f"Running installer from git branch: {ctx.branch}...")
        run_ssh(
            ctx,
            f"python3 /tmp/install-server.py --git --branch {ctx.branch}{domain_arg}{with_arg} --verbose",
            show_full_output_on_error=True,
        )

    print_success("Hop3 installation completed")

    # Verify services
    print_step("Verifying services...")
    run_ssh(ctx, "systemctl status hop3-server --no-pager", show=False, check=False)
    run_ssh(ctx, "systemctl status nginx --no-pager", show=False, check=False)
    print_success("Hop3 services are running")


def configure_server_settings(ctx: DeployContext) -> None:
    """Configure server settings (secret key, logging, etc.)."""
    print_step("Configuring server settings...")

    # Use the existing configure script from demos/lib/scripts
    scripts_dir = ctx.project_root / "demos" / "lib" / "scripts"
    config_script = scripts_dir / "configure_hop3.py"

    if not config_script.exists():
        print_warning(f"Configuration script not found: {config_script}")
        print_info("Generating secret key manually...")
        # Fallback: generate secret key directly via simple command
        run_ssh(
            ctx,
            "grep -q HOP3_SECRET_KEY /home/hop3/hop3-server.toml 2>/dev/null || "
            "echo 'HOP3_SECRET_KEY = \"'$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')'\"\n"
            "HOP3_LOG_LEVEL = \"DEBUG\"' >> /home/hop3/hop3-server.toml",
            show=False,
        )
    else:
        # Copy script to server via scp
        run_local(
            f"scp -o StrictHostKeyChecking=accept-new {config_script} {ctx.ssh_target}:/tmp/configure_hop3.py",
            show=False,
        )
        # Execute with hop3's venv Python (has toml installed)
        run_ssh(ctx, "/home/hop3/venv/bin/python /tmp/configure_hop3.py", show=False)
        run_ssh(ctx, "rm -f /tmp/configure_hop3.py", show=False)

    # Restart server to apply
    print_step("Restarting hop3-server to apply configuration...")
    run_ssh(ctx, "systemctl restart hop3-server", show=False)
    time.sleep(2)
    print_success("Server settings configured")


def update_hop3_server(ctx: DeployContext) -> None:
    """Update hop3-server on the remote server."""
    print_header("Updating hop3-server")

    if ctx.use_local_code:
        sync_local_code(ctx)
        print_step("Installing from local path...")
        run_ssh(
            ctx,
            "/home/hop3/venv/bin/pip install --upgrade /tmp/hop3-server",
            show=False,
        )
    else:
        print_step("Building hop3-server package locally...")
        result = run_local(
            f"cd {ctx.project_root} && uv build packages/hop3-server",
            show=False,
            check=False,
        )
        if result.returncode != 0:
            print_error("Failed to build hop3-server package")
            raise CommandError("Failed to build hop3-server package")

        # Find the built wheel
        wheels = list(ctx.dist_path.glob("hop3_server-*.whl"))
        if not wheels:
            print_error("No wheel file found after build")
            raise CommandError("No wheel file found after build")
        wheel_path = max(wheels, key=lambda p: p.stat().st_mtime)

        print_step(f"Copying {wheel_path.name} to server...")
        run_local(
            f"scp -o StrictHostKeyChecking=accept-new {wheel_path} {ctx.ssh_target}:/tmp/",
            show=False,
        )

        print_step("Installing hop3-server on server...")
        run_ssh(
            ctx,
            f"/home/hop3/venv/bin/pip install --upgrade /tmp/{wheel_path.name}",
            show=False,
        )

    # Restart hop3-server
    print_step("Restarting hop3-server...")
    run_ssh(ctx, "systemctl restart hop3-server", show=False)
    time.sleep(2)
    print_success("hop3-server updated and restarted")


def configure_cli(ctx: DeployContext) -> None:
    """Configure the local Hop3 CLI."""
    print_header("Configuring local CLI")

    # Check if hop3 CLI is available
    print_step("Checking hop3 CLI availability...")
    result = subprocess.run(
        "which hop3", shell=True, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        print_warning("hop3 CLI not found. Install it with: pip install hop3-cli")
        return

    print_success("hop3 CLI found")

    # Create/login admin user
    print_step(f"Setting up admin user '{ctx.admin_user}'...")
    init_cmd = (
        f"echo '{ctx.admin_password}' | hop3 init "
        f"--ssh {ctx.ssh_target} "
        f"--username {ctx.admin_user} "
        f"--email {ctx.admin_email} "
        f"--server http://{ctx.server_ip}:8000 "
        f"--password-stdin --yes"
    )

    result = subprocess.run(
        init_cmd, shell=True, capture_output=True, text=True, check=False
    )

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
            if result.returncode != 0:
                print_warning("Failed to login - you may need to configure CLI manually")
                return
            print_success(f"Logged in as '{ctx.admin_user}'")
        else:
            print_warning("Failed to create admin user - you may need to configure CLI manually")
            if result.stderr:
                print_info(result.stderr.strip())
            return
    else:
        print_success(f"Admin user '{ctx.admin_user}' created")

    # Verify authentication
    print_step("Verifying authentication...")
    result = subprocess.run(
        "hop3 auth:whoami", shell=True, capture_output=True, text=True, check=False
    )
    if result.returncode == 0:
        print_success("Authentication verified")
    else:
        print_warning("Authentication verification failed")


def fetch_server_logs(ctx: DeployContext, lines: int = 30) -> str:
    """Fetch recent hop3-server logs from the remote server."""
    result = subprocess.run(
        [
            "ssh",
            "-o", "StrictHostKeyChecking=accept-new",
            ctx.ssh_target,
            f"journalctl -u hop3-server -n {lines} --no-pager 2>/dev/null || echo 'Could not fetch logs'",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout


def resolve_hostname_to_ip(hostname: str) -> str:
    """Resolve a hostname to an IP address.

    Returns the IP if resolvable, otherwise returns the original hostname.
    """
    try:
        return socket.gethostbyname(hostname)
    except socket.gaierror:
        return hostname


def verify_server_running(ctx: DeployContext, max_retries: int = 15) -> bool:
    """Verify the Hop3 server is responding to HTTP requests.

    Args:
        ctx: Deployment context
        max_retries: Maximum number of retries (2 seconds apart)

    Returns:
        True if server is responding, False otherwise
    """
    print_header("Verifying Server Accessibility")

    # Resolve hostname to IP to avoid mDNS/Bonjour timeout issues with curl
    server_ip = resolve_hostname_to_ip(ctx.server_ip)
    if server_ip != ctx.server_ip:
        print_info(f"Resolved {ctx.server_ip} to {server_ip}")

    server_url = f"http://{server_ip}:8000"
    rpc_url = f"{server_url}/rpc"

    # Wait a moment for server to fully start
    print_step("Waiting for server to initialize...")
    time.sleep(3)

    print_step(f"Checking {server_url}...")

    for attempt in range(1, max_retries + 1):
        # Try to reach the RPC endpoint
        try:
            result = subprocess.run(
                [
                    "curl",
                    "-s",
                    "-o", "/dev/null",
                    "-w", "%{http_code}",
                    "--connect-timeout", "5",
                    "--max-time", "10",
                    rpc_url,
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            http_code = result.stdout.strip()

            # Any response means server is up (even 405 Method Not Allowed is fine for GET on RPC)
            if http_code and http_code != "000":
                print_success(f"Server responding (HTTP {http_code})")

                # Also verify via hop3 CLI if available
                cli_result = subprocess.run(
                    ["hop3", "app:list"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if cli_result.returncode == 0:
                    print_success("CLI can connect to server")
                else:
                    print_warning("CLI connection failed - authentication may be needed")

                return True

        except OSError:
            pass

        if attempt < max_retries:
            print_info(f"Attempt {attempt}/{max_retries} failed, retrying in 2s...")
            time.sleep(2)

    print_error(f"Server not responding at {server_url} after {max_retries} attempts")

    # Fetch and display server logs
    print_info("Fetching server logs for diagnosis...")
    logs = fetch_server_logs(ctx, lines=40)
    if logs:
        print(f"\n{Colors.CYAN}--- hop3-server logs ---{Colors.NC}")
        print(logs)
        print(f"{Colors.CYAN}--- end logs ---{Colors.NC}\n")

    return False


def show_status(ctx: DeployContext) -> None:
    """Show server status after deployment."""
    print_header("Server Status")

    # Check services
    print_step("hop3-server status:")
    result = run_ssh(ctx, "systemctl is-active hop3-server", show=False, check=False)
    status = result.stdout.strip()
    if status == "active":
        print_success("hop3-server is running")
    else:
        print_warning(f"hop3-server status: {status}")

    print_step("nginx status:")
    result = run_ssh(ctx, "systemctl is-active nginx", show=False, check=False)
    status = result.stdout.strip()
    if status == "active":
        print_success("nginx is running")
    else:
        print_warning(f"nginx status: {status}")

    # Show URLs
    print()
    print(f"  {Colors.CYAN}Server:{Colors.NC} http://{ctx.server_ip}:8000/")
    if ctx.admin_domain:
        print(f"  {Colors.CYAN}Admin UI:{Colors.NC} https://{ctx.admin_domain}/")
    print(f"  {Colors.CYAN}SSH:{Colors.NC} {ctx.ssh_target}")
    print()
    print(f"  {Colors.CYAN}Admin user:{Colors.NC} {ctx.admin_user}")
    print(f"  {Colors.CYAN}Admin password:{Colors.NC} {ctx.admin_password}")


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    epilog = """
Examples:
  python scripts/deploy-server.py --host 192.168.1.100                    Fresh install
  python scripts/deploy-server.py --host 192.168.1.100 -l                 Use local code
  python scripts/deploy-server.py --host 192.168.1.100 --skip-install     Update only
  python scripts/deploy-server.py --host 192.168.1.100 --clean-before     Clean reinstall
  python scripts/deploy-server.py --host 192.168.1.100 --with docker,mysql
"""

    parser = argparse.ArgumentParser(
        prog="python scripts/deploy-server.py",
        description="Deploy Hop3 to a remote server for development/testing.",
        epilog=textwrap.dedent(epilog),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Required
    parser.add_argument(
        "-H", "--host",
        required=True,
        metavar="HOST",
        help="Target server IP address or hostname",
    )

    # Server options
    server = parser.add_argument_group("Server Options")
    server.add_argument(
        "--ssh-user",
        default="root",
        metavar="USER",
        help="SSH user for server connection (default: root)",
    )
    server.add_argument(
        "--admin-domain",
        metavar="DOMAIN",
        help="Domain for Hop3 admin UI (e.g., hop3.example.com)",
    )

    # Installation options
    install = parser.add_argument_group("Installation Options")
    install.add_argument(
        "--skip-install",
        action="store_true",
        help="Skip Hop3 installation (assume already installed, just update)",
    )
    install.add_argument(
        "--clean-before",
        action="store_true",
        help="Clean server completely before running (removes /home/hop3, database, all apps)",
    )
    install.add_argument(
        "-l", "--local",
        action="store_true",
        dest="use_local_code",
        help="Sync local hop3-server code via rsync instead of installing from git",
    )
    install.add_argument(
        "--branch",
        default="devel",
        metavar="BRANCH",
        help="Git branch to install from (default: devel)",
    )
    install.add_argument(
        "--with",
        dest="with_features",
        metavar="FEATURES",
        help="Optional features to install: docker,mysql,redis,all (default: all)",
    )

    # Authentication
    auth = parser.add_argument_group("Authentication")
    auth.add_argument(
        "--admin-user",
        default="admin",
        metavar="USER",
        help="Admin username to create (default: admin)",
    )
    auth.add_argument(
        "--admin-email",
        default="admin@example.com",
        metavar="EMAIL",
        help="Admin email address (default: admin@example.com)",
    )
    auth.add_argument(
        "--admin-password",
        metavar="PWD",
        help="Admin password (auto-generated if not specified)",
    )
    auth.add_argument(
        "--no-cli-setup",
        action="store_true",
        help="Skip local CLI configuration",
    )

    # Output
    output = parser.add_argument_group("Output")
    output.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed output",
    )

    return parser


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Parse features
    features = []
    if args.with_features:
        features = [f.strip() for f in args.with_features.split(",")]

    # Generate admin password if not provided
    admin_password = args.admin_password or secrets.token_urlsafe(16)

    # Create context
    ctx = DeployContext(
        server_ip=args.host,
        ssh_user=args.ssh_user,
        admin_domain=args.admin_domain,
        admin_user=args.admin_user,
        admin_email=args.admin_email,
        admin_password=admin_password,
        skip_install=args.skip_install,
        use_local_code=args.use_local_code,
        clean_before=args.clean_before,
        verbose=args.verbose,
        branch=args.branch,
        with_features=features,
    )

    # Print banner
    print(f"\n{Colors.BLUE}{'=' * 50}{Colors.NC}")
    print(f"{Colors.BLUE}  Hop3 Server Deployment{Colors.NC}")
    print(f"{Colors.BLUE}{'=' * 50}{Colors.NC}")
    print()
    print(f"  Target: {ctx.ssh_target}")
    print(f"  Mode: {'Update' if ctx.skip_install else 'Install'}")
    if ctx.use_local_code:
        print(f"  Source: Local code (rsync)")
    else:
        print(f"  Source: Git branch '{ctx.branch}'")
    if ctx.clean_before:
        print(f"  {Colors.YELLOW}Clean install: Yes{Colors.NC}")
    print()

    try:
        # Phase 1: Prerequisites
        print_header("Checking prerequisites")
        verify_ssh_access(ctx)

        version = check_ubuntu_version(ctx)
        if not version:
            return 1

        # Clean if requested
        if ctx.clean_before:
            clean_server(ctx)

        # Phase 2: Install or update
        hop3_installed = check_hop3_installed(ctx)

        if ctx.skip_install:
            if not hop3_installed:
                print_error("Hop3 is not installed and --skip-install was specified")
                return 1
            print_info("Skipping installation (--skip-install)")
            update_hop3_server(ctx)
        elif not hop3_installed:
            install_hop3(ctx)
        else:
            update_hop3_server(ctx)

        # Configure server settings (secret key, etc.)
        configure_server_settings(ctx)

        # Phase 3: Configure CLI (optional)
        if not args.no_cli_setup:
            configure_cli(ctx)

        # Phase 4: Verify server is accessible
        if not verify_server_running(ctx):
            print_error("Server verification failed!")
            print_info("The server was deployed but is not responding to HTTP requests.")
            print_info(f"Check the server logs: ssh {ctx.ssh_target} journalctl -u hop3-server -n 50")
            return 1

        # Phase 5: Show status
        show_status(ctx)

        print(f"{Colors.GREEN}Deployment completed successfully!{Colors.NC}\n")
        return 0

    except CommandError as e:
        print_error(str(e))
        return e.returncode
    except KeyboardInterrupt:
        print()
        print_error("Deployment interrupted by user")
        return 130


if __name__ == "__main__":
    sys.exit(main())
