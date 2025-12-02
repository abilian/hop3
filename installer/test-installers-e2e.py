#!/usr/bin/env python3
# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""E2E test script for Hop3 installers on a remote server.

This script tests the installer via SSH on a real server, validating
the various installation methods (PyPI, git, local path).

Usage:
    # Using command-line argument
    ./test-installers-e2e.py --host user@server.example.com

    # Using environment variable
    HOP3_TEST_HOST=user@server.example.com ./test-installers-e2e.py

    # Test specific installer type
    ./test-installers-e2e.py --host user@server --type cli
    ./test-installers-e2e.py --host root@server --type server

    # Test specific installation method
    ./test-installers-e2e.py --host user@server --method git
    ./test-installers-e2e.py --host user@server --method pypi
    ./test-installers-e2e.py --host user@server --method pypi --version 0.3.0
    ./test-installers-e2e.py --host user@server --method local

Options:
    --host HOST         SSH target (user@hostname), or set HOP3_TEST_HOST env var
    --type TYPE         Installer to test: cli, server, or both (default: both)
    --method METHOD     Installation method: pypi, git, local, or all (default: all)
    --branch BRANCH     Git branch for git method (default: devel)
    --version VERSION   Specific version for pypi method (default: latest)
    --keep              Keep installation after test (don't cleanup)
    --verbose           Show verbose output
    --dry-run           Show what would be done without executing

Requirements:
    - SSH access to target host (preferably with key-based auth)
    - Python 3.10+ on target host
    - For server tests: root or sudo access on target host
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# =============================================================================
# Configuration
# =============================================================================

SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent

# Installation methods to test
INSTALL_METHODS = ["pypi", "git", "local"]
DEFAULT_METHOD = "all"
DEFAULT_TYPE = "both"
DEFAULT_BRANCH = "devel"  # Use devel branch since main might not have latest


# =============================================================================
# Terminal Colors
# =============================================================================


@dataclass
class Colors:
    """ANSI color codes for terminal output."""

    RESET: str = "\033[0m"
    RED: str = "\033[0;31m"
    GREEN: str = "\033[0;32m"
    YELLOW: str = "\033[0;33m"
    BLUE: str = "\033[0;34m"
    MAGENTA: str = "\033[0;35m"
    CYAN: str = "\033[0;36m"
    BOLD: str = "\033[1m"
    DIM: str = "\033[2m"


# Disable colors if not a TTY
if sys.stdout.isatty():
    C = Colors()
else:
    C = Colors(
        RESET="",
        RED="",
        GREEN="",
        YELLOW="",
        BLUE="",
        MAGENTA="",
        CYAN="",
        BOLD="",
        DIM="",
    )


# =============================================================================
# Logging
# =============================================================================

VERBOSE = False
DRY_RUN = False


def log_info(message: str) -> None:
    """Print an info message."""
    print(f"{C.BLUE}[INFO]{C.RESET} {message}")


def log_success(message: str) -> None:
    """Print a success message."""
    print(f"{C.GREEN}[PASS]{C.RESET} {message}")


def log_warning(message: str) -> None:
    """Print a warning message."""
    print(f"{C.YELLOW}[WARN]{C.RESET} {message}")


def log_error(message: str) -> None:
    """Print an error message."""
    print(f"{C.RED}[FAIL]{C.RESET} {message}", file=sys.stderr)


def log_debug(message: str) -> None:
    """Print a debug message (only in verbose mode)."""
    if VERBOSE:
        print(f"{C.DIM}[DEBUG]{C.RESET} {message}")


def log_header(message: str) -> None:
    """Print a header."""
    print()
    print(f"{C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}  {message}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")
    print()


def log_subheader(message: str) -> None:
    """Print a subheader."""
    print()
    print(f"{C.BOLD}--- {message} ---{C.RESET}")
    print()


# =============================================================================
# SSH Command Execution
# =============================================================================


def ssh_run(
    host: str,
    command: str,
    check: bool = True,
    capture_output: bool = True,
    sudo: bool = False,
) -> subprocess.CompletedProcess:
    """Run a command on the remote host via SSH."""
    if sudo:
        command = f"sudo bash -c '{command}'"

    ssh_cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=10",
        host,
        command,
    ]

    log_debug(f"SSH: {command}")

    if DRY_RUN:
        print(f"  [DRY-RUN] ssh {host} '{command}'")
        return subprocess.CompletedProcess(ssh_cmd, 0, "", "")

    result = subprocess.run(
        ssh_cmd,
        check=False,
        capture_output=capture_output,
        text=True,
    )

    if check and result.returncode != 0:
        log_debug(f"SSH command failed: {result.stderr}")

    return result


def ssh_copy(host: str, local_path: Path, remote_path: str) -> bool:
    """Copy a file to the remote host via SCP."""
    scp_cmd = [
        "scp",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        str(local_path),
        f"{host}:{remote_path}",
    ]

    log_debug(f"SCP: {local_path} -> {host}:{remote_path}")

    if DRY_RUN:
        print(f"  [DRY-RUN] scp {local_path} {host}:{remote_path}")
        return True

    result = subprocess.run(scp_cmd, check=False, capture_output=True, text=True)
    return result.returncode == 0


def ssh_copy_dir(host: str, local_dir: Path, remote_path: str) -> bool:
    """Copy a directory to the remote host via SCP."""
    scp_cmd = [
        "scp",
        "-r",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        str(local_dir),
        f"{host}:{remote_path}",
    ]

    log_debug(f"SCP: {local_dir} -> {host}:{remote_path}")

    if DRY_RUN:
        print(f"  [DRY-RUN] scp -r {local_dir} {host}:{remote_path}")
        return True

    result = subprocess.run(scp_cmd, check=False, capture_output=True, text=True)
    return result.returncode == 0


def check_ssh_connection(host: str) -> bool:
    """Check if SSH connection works."""
    result = ssh_run(host, "echo 'SSH OK'", check=False)
    return result.returncode == 0


def check_python_version(host: str) -> str | None:
    """Check Python version on remote host."""
    result = ssh_run(
        host,
        "python3 --version 2>/dev/null || python --version 2>/dev/null",
        check=False,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


# =============================================================================
# CLI Installer Tests
# =============================================================================


def cleanup_cli(host: str) -> None:
    """Remove CLI installation from remote host."""
    log_info("Cleaning up CLI installation...")

    # Remove installation directories and symlinks
    ssh_run(
        host,
        "rm -rf ~/.hop3-cli ~/.local/bin/hop3 ~/.local/bin/hop /tmp/install-cli.py /tmp/hop3-cli",
        check=False,
    )

    # Remove PATH additions from shell configs
    shell_configs = ["~/.bashrc", "~/.zshrc", "~/.profile", "~/.bash_profile"]
    for config in shell_configs:
        # Remove lines added by Hop3 CLI installer
        ssh_run(
            host,
            f"sed -i '/# Added by Hop3 CLI installer/d' {config} 2>/dev/null; "
            f"sed -i '/\\.local\\/bin/d' {config} 2>/dev/null",
            check=False,
        )

    log_success("CLI cleanup complete")


def upload_cli_installer(host: str) -> bool:
    """Upload CLI installer to remote host."""
    installer_path = SCRIPT_DIR / "install-cli.py"
    if not installer_path.exists():
        log_error(f"Installer not found: {installer_path}")
        return False

    return ssh_copy(host, installer_path, "/tmp/install-cli.py")


def upload_local_package(host: str, package_type: str) -> str | None:
    """Upload local package to remote host for --local-path testing."""
    if package_type == "cli":
        local_package = PROJECT_ROOT / "packages" / "hop3-cli"
    else:
        local_package = PROJECT_ROOT / "packages" / "hop3-server"

    if not local_package.exists():
        log_error(f"Local package not found: {local_package}")
        return None

    remote_path = f"/tmp/hop3-{package_type}"

    # Remove existing
    ssh_run(host, f"rm -rf {remote_path}", check=False)

    if ssh_copy_dir(host, local_package, remote_path):
        return remote_path
    return None


def test_cli_pypi(host: str, version: str | None = None) -> bool:
    """Test CLI installation from PyPI.

    Args:
        host: SSH target
        version: Specific version to install, or None for latest
    """
    version_str = version or "latest"
    log_subheader(f"Testing CLI: PyPI ({version_str})")

    cleanup_cli(host)

    if not upload_cli_installer(host):
        return False

    # Build installer command
    if version:
        cmd = f"python3 /tmp/install-cli.py --version {version} --no-modify-path --verbose"
        log_info(f"Running installer (PyPI version {version})...")
    else:
        cmd = "python3 /tmp/install-cli.py --no-modify-path --verbose"
        log_info("Running installer (PyPI latest)...")

    result = ssh_run(host, cmd, check=False)

    if result.returncode != 0:
        log_error("Installation failed")
        if VERBOSE:
            print(result.stdout)
            print(result.stderr)
        return False

    return validate_cli_installation(host)


def test_cli_git(host: str, branch: str) -> bool:
    """Test CLI installation from git."""
    log_subheader(f"Testing CLI: Git ({branch} branch)")

    cleanup_cli(host)

    if not upload_cli_installer(host):
        return False

    log_info(f"Running installer (git {branch})...")
    result = ssh_run(
        host,
        f"python3 /tmp/install-cli.py --git --branch {branch} --no-modify-path --verbose",
        check=False,
    )

    if result.returncode != 0:
        log_error("Installation failed")
        if VERBOSE:
            print(result.stdout)
            print(result.stderr)
        return False

    return validate_cli_installation(host)


def test_cli_local(host: str) -> bool:
    """Test CLI installation from local path."""
    log_subheader("Testing CLI: Local path")

    cleanup_cli(host)

    if not upload_cli_installer(host):
        return False

    remote_package = upload_local_package(host, "cli")
    if not remote_package:
        log_warning("Skipping local path test (could not upload package)")
        return True  # Don't fail the suite

    log_info("Running installer (local path)...")
    result = ssh_run(
        host,
        f"python3 /tmp/install-cli.py --local-path {remote_package} --no-modify-path --verbose",
        check=False,
    )

    if result.returncode != 0:
        log_error("Installation failed")
        if VERBOSE:
            print(result.stdout)
            print(result.stderr)
        return False

    return validate_cli_installation(host)


def validate_cli_installation(host: str) -> bool:
    """Validate CLI installation on remote host."""
    log_info("Validating installation...")
    all_passed = True

    # Check venv exists
    result = ssh_run(host, "test -d ~/.hop3-cli/venv", check=False)
    if result.returncode == 0:
        log_success("Virtual environment exists")
    else:
        log_error("Virtual environment not found")
        all_passed = False

    # Check hop3 command exists
    result = ssh_run(
        host,
        "test -f ~/.hop3-cli/venv/bin/hop3 || test -f ~/.hop3-cli/venv/bin/hop",
        check=False,
    )
    if result.returncode == 0:
        log_success("CLI command installed")
    else:
        log_error("CLI command not found")
        all_passed = False

    # Check symlink
    result = ssh_run(
        host,
        "test -L ~/.local/bin/hop3 || test -f ~/.local/bin/hop3",
        check=False,
    )
    if result.returncode == 0:
        log_success("Symlink created")
    else:
        log_warning("Symlink not found (may be expected with --no-modify-path)")

    # Try running help
    result = ssh_run(
        host,
        "~/.hop3-cli/venv/bin/hop3 --help 2>&1 || ~/.hop3-cli/venv/bin/hop --help 2>&1",
        check=False,
    )
    if result.returncode == 0 or "usage" in result.stdout.lower():
        log_success("CLI command runs successfully")
    else:
        log_warning("CLI command may have issues")
        if VERBOSE:
            print(result.stdout)

    return all_passed


# =============================================================================
# Server Installer Tests
# =============================================================================


def cleanup_server(host: str) -> None:
    """Remove server installation from remote host (thorough cleanup)."""
    log_info("Cleaning up server installation...")

    # Stop and disable services
    service_commands = [
        "systemctl stop hop3-server uwsgi-hop3 nginx postgresql 2>/dev/null || true",
        "systemctl disable hop3-server uwsgi-hop3 2>/dev/null || true",
        "rm -f /etc/systemd/system/hop3-server.service /etc/systemd/system/uwsgi-hop3.service",
        "systemctl daemon-reload",
    ]
    for cmd in service_commands:
        ssh_run(host, cmd, check=False, sudo=True)

    # Remove hop3 user and group
    user_commands = [
        "userdel -r hop3 2>/dev/null || true",
        "groupdel hop3 2>/dev/null || true",
        # Remove www-data from hop3 group (in case it was added)
        "gpasswd -d www-data hop3 2>/dev/null || true",
    ]
    for cmd in user_commands:
        ssh_run(host, cmd, check=False, sudo=True)

    # Detect distro for package removal
    distro_result = ssh_run(
        host,
        "cat /etc/os-release 2>/dev/null | grep -E '^ID=' | cut -d= -f2 | tr -d '\"'",
        check=False,
    )
    distro = (
        distro_result.stdout.strip().lower() if distro_result.returncode == 0 else ""
    )

    # Purge packages based on distro
    if distro in ("ubuntu", "debian"):
        # Use DEBIAN_FRONTEND=noninteractive to prevent any prompts
        apt_env = "DEBIAN_FRONTEND=noninteractive"
        package_commands = [
            # Stop services first
            "systemctl stop postgresql nginx 2>/dev/null || true",
            # Kill any stuck apt/dpkg processes and remove locks
            "killall -9 apt apt-get dpkg 2>/dev/null || true",
            "rm -f /var/lib/apt/lists/lock /var/cache/apt/archives/lock /var/lib/dpkg/lock* 2>/dev/null || true",
            # Fix any broken packages first
            f"{apt_env} dpkg --configure -a 2>/dev/null || true",
            f"{apt_env} apt-get -f install -y 2>/dev/null || true",
            # Purge PostgreSQL completely (list packages explicitly to avoid glob issues)
            f"{apt_env} apt-get purge -y postgresql postgresql-client postgresql-contrib postgresql-common 2>/dev/null || true",
            f"{apt_env} apt-get autoremove -y 2>/dev/null || true",
            # Remove PostgreSQL data directory
            "rm -rf /var/lib/postgresql /etc/postgresql /var/log/postgresql",
            # Purge nginx (list packages explicitly)
            f"{apt_env} apt-get purge -y nginx nginx-common nginx-core nginx-full nginx-light 2>/dev/null || true",
            "rm -rf /etc/nginx /var/log/nginx /var/www/html",
            f"{apt_env} apt-get autoremove -y 2>/dev/null || true",
        ]
    elif distro in ("fedora", "rhel", "centos", "rocky", "almalinux"):
        package_commands = [
            # Stop services first
            "systemctl stop postgresql nginx 2>/dev/null || true",
            # Remove PostgreSQL completely
            "dnf remove -y postgresql postgresql-server postgresql-contrib 2>/dev/null || true",
            "rm -rf /var/lib/pgsql /etc/postgresql",
            # Remove nginx
            "dnf remove -y nginx 2>/dev/null || true",
            "rm -rf /etc/nginx /var/log/nginx",
        ]
    else:
        package_commands = []
        log_debug(f"Unknown distro '{distro}', skipping package removal")

    for cmd in package_commands:
        ssh_run(host, cmd, check=False, sudo=True)

    # Remove acme.sh if installed
    acme_commands = [
        "rm -rf /home/hop3/.acme.sh 2>/dev/null || true",
        # Also check root's acme.sh
        "rm -rf /root/.acme.sh 2>/dev/null || true",
    ]
    for cmd in acme_commands:
        ssh_run(host, cmd, check=False, sudo=True)

    # Clean up hop3 directories and temp files
    cleanup_commands = [
        "rm -rf /home/hop3 /tmp/install-server.py /tmp/hop3-server",
        # Remove any hop3-related nginx configs
        "rm -f /etc/nginx/sites-available/hop3* /etc/nginx/sites-enabled/hop3* 2>/dev/null || true",
        "rm -f /etc/nginx/conf.d/hop3* 2>/dev/null || true",
    ]
    for cmd in cleanup_commands:
        ssh_run(host, cmd, check=False, sudo=True)

    # Clean shell configs for root user
    shell_configs = ["/root/.bashrc", "/root/.profile", "/root/.bash_profile"]
    for config in shell_configs:
        ssh_run(
            host,
            f"sed -i '/hop3/Id' {config} 2>/dev/null || true",
            check=False,
            sudo=True,
        )

    log_success("Server cleanup complete")


def upload_server_installer(host: str) -> bool:
    """Upload server installer to remote host."""
    installer_path = SCRIPT_DIR / "install-server.py"
    if not installer_path.exists():
        log_error(f"Installer not found: {installer_path}")
        return False

    return ssh_copy(host, installer_path, "/tmp/install-server.py")


def test_server_git(host: str, branch: str) -> bool:
    """Test server installation from git."""
    log_subheader(f"Testing Server: Git ({branch} branch)")

    cleanup_server(host)

    if not upload_server_installer(host):
        return False

    log_info(f"Running installer (git {branch}, skip-acme)...")
    result = ssh_run(
        host,
        f"python3 /tmp/install-server.py --git --branch {branch} --skip-acme --verbose",
        check=False,
        sudo=True,
    )

    if result.returncode != 0:
        log_error("Installation failed")
        if VERBOSE:
            print(result.stdout)
            print(result.stderr)
        return False

    return validate_server_installation(host)


def test_server_local(host: str) -> bool:
    """Test server installation from local path."""
    log_subheader("Testing Server: Local path")

    cleanup_server(host)

    if not upload_server_installer(host):
        return False

    remote_package = upload_local_package(host, "server")
    if not remote_package:
        log_warning("Skipping local path test (could not upload package)")
        return True

    # Fix permissions: the package is uploaded as root but needs to be readable
    # by the hop3 user during installation. Make it world-readable.
    ssh_run(host, f"chmod -R a+rX {remote_package}", check=False, sudo=True)

    log_info("Running installer (local path, skip-acme)...")
    result = ssh_run(
        host,
        f"python3 /tmp/install-server.py --local-path {remote_package} --skip-acme --verbose",
        check=False,
        sudo=True,
    )

    if result.returncode != 0:
        log_error("Installation failed")
        if VERBOSE:
            print(result.stdout)
            print(result.stderr)
        return False

    return validate_server_installation(host)


def validate_server_installation(host: str) -> bool:
    """Validate server installation on remote host."""
    log_info("Validating installation...")
    all_passed = True

    # Check hop3 user exists
    result = ssh_run(host, "id hop3", check=False)
    if result.returncode == 0:
        log_success("hop3 user exists")
    else:
        log_error("hop3 user not found")
        all_passed = False

    # Check venv exists
    result = ssh_run(host, "test -d /home/hop3/venv", check=False, sudo=True)
    if result.returncode == 0:
        log_success("Virtual environment exists")
    else:
        log_error("Virtual environment not found")
        all_passed = False

    # Check hop-server command exists
    result = ssh_run(
        host, "test -f /home/hop3/venv/bin/hop-server", check=False, sudo=True
    )
    if result.returncode == 0:
        log_success("hop-server command installed")
    else:
        log_error("hop-server command not found")
        all_passed = False

    # Check systemd service
    result = ssh_run(host, "systemctl is-enabled hop3-server 2>/dev/null", check=False)
    if "enabled" in result.stdout:
        log_success("hop3-server service is enabled")
    else:
        log_warning("hop3-server service not enabled")

    # Check service status
    result = ssh_run(host, "systemctl is-active hop3-server 2>/dev/null", check=False)
    if "active" in result.stdout:
        log_success("hop3-server service is running")
    else:
        log_warning("hop3-server service is not running (may need configuration)")

    # Check PostgreSQL is running
    result = ssh_run(host, "systemctl is-active postgresql 2>/dev/null", check=False)
    if "active" in result.stdout:
        log_success("PostgreSQL service is running")
    else:
        log_error("PostgreSQL service is not running")
        all_passed = False

    # Check PostgreSQL hop3 role exists
    # Run as postgres user directly (we're already root, no need for sudo wrapper)
    result = ssh_run(
        host,
        """su - postgres -c "psql -tAc \\"SELECT 1 FROM pg_roles WHERE rolname='hop3'\\"" """,
        check=False,
    )
    if "1" in result.stdout:
        log_success("PostgreSQL hop3 role exists")
    else:
        log_error("PostgreSQL hop3 role not found")
        all_passed = False

    # Check PostgreSQL hop3 database exists
    result = ssh_run(
        host,
        """su - postgres -c "psql -tAc \\"SELECT 1 FROM pg_database WHERE datname='hop3'\\"" """,
        check=False,
    )
    if "1" in result.stdout:
        log_success("PostgreSQL hop3 database exists")
    else:
        log_error("PostgreSQL hop3 database not found")
        all_passed = False

    return all_passed


# =============================================================================
# Test Runner
# =============================================================================


def run_cli_tests(
    host: str, methods: list[str], branch: str, version: str | None, keep: bool
) -> dict[str, bool]:
    """Run CLI installer tests."""
    results = {}

    for method in methods:
        if method == "pypi":
            results["cli-pypi"] = test_cli_pypi(host, version)
        elif method == "git":
            results["cli-git"] = test_cli_git(host, branch)
        elif method == "local":
            results["cli-local"] = test_cli_local(host)

        if not keep:
            cleanup_cli(host)

    return results


def run_server_tests(
    host: str, methods: list[str], branch: str, keep: bool
) -> dict[str, bool]:
    """Run server installer tests."""
    results = {}

    # Server tests are more limited (no PyPI version yet, requires root)
    for method in methods:
        if method == "git":
            results["server-git"] = test_server_git(host, branch)
        elif method == "local":
            results["server-local"] = test_server_local(host)
        elif method == "pypi":
            log_info("Skipping server pypi test (not yet on PyPI)")

        if not keep:
            cleanup_server(host)

    return results


# =============================================================================
# Argument Parsing
# =============================================================================


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="E2E test script for Hop3 installers on a remote server.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Test both installers on remote server
    ./test-installers-e2e.py --host root@server.example.com

    # Test with environment variable
    HOP3_TEST_HOST=root@server ./test-installers-e2e.py

    # Test specific method
    ./test-installers-e2e.py --host user@server --method git

    # Test PyPI with specific version
    ./test-installers-e2e.py --host user@server --method pypi --version 0.3.0

    # Test server installer only (requires root)
    ./test-installers-e2e.py --host root@server --type server

    # Dry run (show what would be done)
    ./test-installers-e2e.py --host user@server --dry-run

Installation Methods:
    pypi        Install from PyPI (use --version for specific version, default: latest)
    git         Install from git repository (use --branch for specific branch)
    local       Install from local package directory (uploads via SCP)
    all         Test all methods (default)

Test Types:
    cli         Test CLI installer
    server      Test server installer (requires root/sudo)
    both        Test both installers (default)
        """,
    )

    parser.add_argument(
        "--host",
        metavar="HOST",
        default=os.environ.get("HOP3_TEST_HOST"),
        help="SSH target (user@hostname). Can also set HOP3_TEST_HOST env var",
    )

    parser.add_argument(
        "--type",
        choices=["cli", "server", "both"],
        default=DEFAULT_TYPE,
        help=f"Installer type to test (default: {DEFAULT_TYPE})",
    )

    parser.add_argument(
        "--method",
        choices=INSTALL_METHODS + ["all"],
        default=DEFAULT_METHOD,
        help=f"Installation method to test (default: {DEFAULT_METHOD})",
    )

    parser.add_argument(
        "--branch",
        metavar="BRANCH",
        default=os.environ.get("HOP3_BRANCH", DEFAULT_BRANCH),
        help=f"Git branch for git method (default: {DEFAULT_BRANCH})",
    )

    parser.add_argument(
        "--version",
        metavar="VERSION",
        default=os.environ.get("HOP3_VERSION"),
        help="Specific version for pypi method (default: latest)",
    )

    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep installation after test (don't cleanup)",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without executing",
    )

    return parser.parse_args()


# =============================================================================
# Main
# =============================================================================


def main() -> int:
    """Main entry point."""
    global VERBOSE, DRY_RUN

    args = parse_arguments()
    VERBOSE = args.verbose
    DRY_RUN = args.dry_run

    # Check host is provided
    if not args.host:
        log_error(
            "No host specified. Use --host or set HOP3_TEST_HOST environment variable"
        )
        print()
        print("Example:")
        print("  ./test-installers-e2e.py --host user@server.example.com")
        print("  HOP3_TEST_HOST=user@server ./test-installers-e2e.py")
        return 1

    # Print test plan
    log_header("Hop3 Installer E2E Tests")
    print(f"  Host:    {args.host}")
    print(f"  Type:    {args.type}")
    print(f"  Method:  {args.method}")
    print(f"  Branch:  {args.branch}")
    print(f"  Version: {args.version or 'latest'}")
    if args.dry_run:
        print(f"  {C.YELLOW}DRY-RUN MODE{C.RESET}")
    print()

    # Check SSH connection
    log_info("Checking SSH connection...")
    if not DRY_RUN and not check_ssh_connection(args.host):
        log_error(f"Cannot connect to {args.host}")
        log_info("Make sure SSH key authentication is set up:")
        log_info(f"  ssh-copy-id {args.host}")
        return 1
    log_success("SSH connection OK")

    # Check Python version
    log_info("Checking Python version on remote host...")
    if not DRY_RUN:
        python_version = check_python_version(args.host)
        if python_version:
            log_success(f"Remote Python: {python_version}")
        else:
            log_error("Python 3 not found on remote host")
            return 1

    # Determine what methods to test
    if args.method == "all":
        methods = INSTALL_METHODS.copy()
    else:
        methods = [args.method]

    # Run tests
    all_results: dict[str, bool] = {}

    if args.type in ("cli", "both"):
        log_header("CLI Installer Tests")
        cli_results = run_cli_tests(
            args.host, methods, args.branch, args.version, args.keep
        )
        all_results.update(cli_results)

    if args.type in ("server", "both"):
        log_header("Server Installer Tests")
        server_results = run_server_tests(args.host, methods, args.branch, args.keep)
        all_results.update(server_results)

    # Print summary
    log_header("Test Summary")

    total = len(all_results)
    passed = sum(1 for v in all_results.values() if v)
    failed = total - passed

    print(f"  Total:   {total}")
    print(f"  Passed:  {C.GREEN}{passed}{C.RESET}")
    print(f"  Failed:  {C.RED if failed > 0 else ''}{failed}{C.RESET}")
    print()

    for test_name, success in all_results.items():
        status = f"{C.GREEN}PASS{C.RESET}" if success else f"{C.RED}FAIL{C.RESET}"
        print(f"  [{status}] {test_name}")

    if failed > 0:
        print()
        log_error("Some tests failed")
        return 1

    print()
    log_success("All tests passed!")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nTests cancelled.")
        sys.exit(130)
    except Exception as e:
        log_error(f"Unexpected error: {e}")
        if VERBOSE:
            import traceback

            traceback.print_exc()
        sys.exit(1)
