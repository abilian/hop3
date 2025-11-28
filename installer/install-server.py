#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Hop3 Server Installer

A single-file installer for the Hop3 Server.
Uses only Python standard library for maximum portability.
Must be run as root.

Usage:
    curl -LsSf https://hop3.cloud/install-server.py | sudo python3 -
    curl -LsSf https://hop3.cloud/install-server.py | sudo python3 - --git
    sudo python3 install-server.py --help
"""
from __future__ import annotations

# =============================================================================
# Version Check (must run before any 3.10+ features are used at runtime)
# =============================================================================

import sys

MIN_PYTHON = (3, 10)

if sys.version_info < MIN_PYTHON:
    print(f"Error: Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required")
    print(f"Found: Python {sys.version_info.major}.{sys.version_info.minor}")
    print()
    print("Please install a newer Python version:")
    print("  Ubuntu/Debian: sudo apt install python3.11")
    print("  Fedora:        sudo dnf install python3.11")
    sys.exit(1)

# =============================================================================
# Imports (standard library only)
# =============================================================================

import argparse
import grp
import itertools
import os
import pwd
import shutil
import subprocess
import threading
import time
from pathlib import Path

# =============================================================================
# Configuration
# =============================================================================

PACKAGE_NAME = "hop3-server"
GIT_REPO = "https://github.com/abilian/hop3.git"
GIT_SUBDIR = "packages/hop3-server"
DEFAULT_BRANCH = "main"

HOP3_USER = "hop3"
HOP3_GROUP = "hop3"
HOME_DIR = Path("/home") / HOP3_USER
VENV_DIR = HOME_DIR / "venv"

# System dependencies by distribution
DEBIAN_PACKAGES = [
    "bc", "git", "sudo", "cron", "build-essential",
    "libpcre3-dev", "zlib1g-dev",
    "nginx", "postgresql", "postgresql-contrib",
    "python3-dev", "python3-pip", "python3-venv",
    "curl", "wget", "rsync", "socat",
    "libjpeg-dev", "libpng-dev", "libwebp-dev",
    "libpq-dev", "libffi-dev", "libssl-dev",
]

FEDORA_PACKAGES = [
    "bc", "git", "sudo", "cronie", "gcc", "gcc-c++", "make",
    "pcre-devel", "zlib-devel",
    "nginx", "postgresql-server", "postgresql-contrib",
    "python3-devel", "python3-pip",
    "curl", "wget", "rsync", "socat",
    "libjpeg-devel", "libpng-devel", "libwebp-devel",
    "libpq-devel", "libffi-devel", "openssl-devel",
]

# Systemd service units
SYSTEMD_UNIT = """[Unit]
Description=Hop3 Server
After=network.target postgresql.service

[Service]
Type=simple
User=hop3
Group=hop3
WorkingDirectory=/home/hop3
ExecStart=/home/hop3/venv/bin/hop-server serve
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""

UWSGI_UNIT = """[Unit]
Description=uWSGI Emperor for Hop3
After=network.target

[Service]
Type=notify
User=hop3
Group=hop3
ExecStart=/home/hop3/venv/bin/uwsgi --emperor /home/hop3/uwsgi-enabled --stats /tmp/hop3-uwsgi-stats.sock
Restart=always
KillSignal=SIGQUIT
NotifyAccess=all

[Install]
WantedBy=multi-user.target
"""

# =============================================================================
# Terminal Output
# =============================================================================


class Colors:
    """ANSI color codes."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[0;33m"
    BLUE = "\033[0;34m"
    CYAN = "\033[0;36m"

    @classmethod
    def disable(cls) -> None:
        for attr in ["RESET", "BOLD", "DIM", "RED", "GREEN", "YELLOW", "BLUE", "CYAN"]:
            setattr(cls, attr, "")


# Disable colors if not a TTY
if not sys.stdout.isatty():
    Colors.disable()


def print_header(title: str) -> None:
    """Print a styled header."""
    print()
    print(f"{Colors.BOLD}{Colors.CYAN}{title}{Colors.RESET}")
    print(f"{Colors.DIM}{'=' * len(title)}{Colors.RESET}")
    print()


def print_step(step: int, total: int, message: str) -> None:
    """Print a step indicator."""
    print(f"\n{Colors.BOLD}[{step}/{total}]{Colors.RESET} {message}")


def print_success(message: str) -> None:
    """Print a success message."""
    print(f"      {Colors.GREEN}✓{Colors.RESET} {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    print(f"      {Colors.BLUE}ℹ{Colors.RESET} {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    print(f"      {Colors.YELLOW}⚠{Colors.RESET} {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    print(f"      {Colors.RED}✗{Colors.RESET} {message}", file=sys.stderr)


def print_detail(message: str) -> None:
    """Print a detail/sub-item."""
    print(f"        {Colors.DIM}{message}{Colors.RESET}")


# =============================================================================
# Spinner for Long Operations
# =============================================================================


class Spinner:
    """A simple terminal spinner for long-running operations."""

    CHARS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, message: str):
        self.message = message
        self.spinning = False
        self.thread: threading.Thread | None = None

    def __enter__(self) -> Spinner:
        if sys.stdout.isatty():
            self.spinning = True
            self.thread = threading.Thread(target=self._spin, daemon=True)
            self.thread.start()
        else:
            print(f"      ... {self.message}")
        return self

    def __exit__(self, *args) -> None:
        self.spinning = False
        if self.thread:
            self.thread.join(timeout=0.5)
        if sys.stdout.isatty():
            print(f"\r{' ' * (len(self.message) + 12)}\r", end="")

    def _spin(self) -> None:
        for char in itertools.cycle(self.CHARS):
            if not self.spinning:
                break
            print(f"\r      {Colors.CYAN}{char}{Colors.RESET} {self.message}", end="", flush=True)
            time.sleep(0.08)


# =============================================================================
# Command Execution
# =============================================================================


class CommandError(Exception):
    """Raised when a command fails."""

    def __init__(self, cmd: list[str], returncode: int, stderr: str):
        self.cmd = cmd
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"Command failed: {' '.join(cmd)}")


def run_cmd(
    cmd: list[str],
    capture: bool = True,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    result = subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        env=run_env,
    )

    if check and result.returncode != 0:
        raise CommandError(cmd, result.returncode, result.stderr or "")

    return result


def run_as_hop3(cmd: str) -> subprocess.CompletedProcess:
    """Run a command as the hop3 user."""
    return run_cmd(["su", "-", HOP3_USER, "-c", cmd])


def cmd_exists(cmd: str) -> bool:
    """Check if a command exists in PATH."""
    return shutil.which(cmd) is not None


# =============================================================================
# System Detection
# =============================================================================


def detect_distro() -> str:
    """Detect the Linux distribution. Returns 'debian', 'fedora', or 'unknown'."""
    os_release = Path("/etc/os-release")
    if os_release.exists():
        content = os_release.read_text()
        if any(d in content.lower() for d in ["ubuntu", "debian", "mint", "pop"]):
            return "debian"
        if any(d in content.lower() for d in ["fedora", "rhel", "centos", "rocky", "alma"]):
            return "fedora"
        if "arch" in content.lower():
            return "arch"
    return "unknown"


def user_exists(username: str) -> bool:
    """Check if a user exists."""
    try:
        pwd.getpwnam(username)
        return True
    except KeyError:
        return False


def group_exists(groupname: str) -> bool:
    """Check if a group exists."""
    try:
        grp.getgrnam(groupname)
        return True
    except KeyError:
        return False


# =============================================================================
# Installation Steps
# =============================================================================


def install_system_deps(distro: str, skip: bool) -> None:
    """Install system dependencies."""
    if skip:
        print_info("Skipping system dependencies (--skip-deps)")
        return

    if distro == "debian":
        with Spinner("Updating package lists..."):
            run_cmd(["apt-get", "update", "-qq"])
        with Spinner("Installing packages (this may take a while)..."):
            run_cmd(
                ["apt-get", "install", "-y", "-qq"] + DEBIAN_PACKAGES,
                env={"DEBIAN_FRONTEND": "noninteractive"},
            )
        print_success(f"Installed {len(DEBIAN_PACKAGES)} packages")

    elif distro == "fedora":
        with Spinner("Installing packages (this may take a while)..."):
            run_cmd(["dnf", "install", "-y", "-q"] + FEDORA_PACKAGES)
        print_success(f"Installed {len(FEDORA_PACKAGES)} packages")

    else:
        print_warning(f"Unknown distro '{distro}', skipping package installation")
        print_detail("You may need to install dependencies manually")


def create_user_and_group() -> None:
    """Create the hop3 user and group."""
    # Create group
    if not group_exists(HOP3_GROUP):
        run_cmd(["groupadd", HOP3_GROUP])
        print_success(f"Created group: {HOP3_GROUP}")
    else:
        print_info(f"Group {HOP3_GROUP} already exists")

    # Create user
    if not user_exists(HOP3_USER):
        run_cmd([
            "useradd", "-m",
            "-g", HOP3_GROUP,
            "-s", "/bin/bash",
            "-d", str(HOME_DIR),
            HOP3_USER,
        ])
        print_success(f"Created user: {HOP3_USER}")
    else:
        print_info(f"User {HOP3_USER} already exists")

    # Ensure home directory exists with correct permissions
    if not HOME_DIR.exists():
        HOME_DIR.mkdir(parents=True, exist_ok=True)
        print_info(f"Created home directory: {HOME_DIR}")

    hop3_uid = pwd.getpwnam(HOP3_USER).pw_uid
    hop3_gid = grp.getgrnam(HOP3_GROUP).gr_gid
    os.chown(HOME_DIR, hop3_uid, hop3_gid)
    os.chmod(HOME_DIR, 0o755)

    # Add www-data to hop3 group
    if user_exists("www-data"):
        run_cmd(["usermod", "-a", "-G", HOP3_GROUP, "www-data"], check=False)
        print_info("Added www-data to hop3 group")


def create_virtual_environment() -> None:
    """Create Python virtual environment."""
    if VENV_DIR.exists():
        shutil.rmtree(VENV_DIR)

    with Spinner("Creating virtual environment..."):
        run_as_hop3(f"python3 -m venv {VENV_DIR}")

    print_success(f"Virtual environment created at {VENV_DIR}")


def install_package(
    version: str | None,
    use_git: bool,
    branch: str,
    local_path: str | None,
    verbose: bool,
) -> None:
    """Install the hop3-server package."""
    pip = f"{VENV_DIR}/bin/pip"

    # Upgrade pip
    with Spinner("Upgrading pip..."):
        run_as_hop3(f"{pip} install --upgrade pip")

    # Determine what to install
    if local_path:
        package_spec = local_path
        source_desc = f"local path ({local_path})"
    elif use_git:
        with Spinner("Installing build tools..."):
            run_as_hop3(f"{pip} install uv")
        package_spec = f"git+{GIT_REPO}@{branch}#subdirectory={GIT_SUBDIR}"
        source_desc = f"git ({branch} branch)"
    elif version:
        package_spec = f"{PACKAGE_NAME}=={version}"
        source_desc = f"PyPI (version {version})"
    else:
        package_spec = PACKAGE_NAME
        source_desc = "PyPI (latest)"

    # Install
    with Spinner(f"Installing hop3-server from {source_desc}..."):
        run_as_hop3(f"{pip} install '{package_spec}'")

    print_success("hop3-server installed successfully")


def run_hop3_setup() -> None:
    """Run hop3 setup command."""
    hop_server = f"{VENV_DIR}/bin/hop-server"

    with Spinner("Running initial setup..."):
        run_as_hop3(f"{hop_server} setup")

    print_success("Hop3 initial setup complete")


def setup_ssh_keys() -> None:
    """Copy root SSH keys to hop3 user if available."""
    root_keys = Path("/root/.ssh/authorized_keys")

    if not root_keys.exists():
        print_info("No root SSH keys found, skipping")
        return

    content = root_keys.read_text().strip()
    if not content:
        print_info("Root SSH keys file is empty, skipping")
        return

    hop_server = f"{VENV_DIR}/bin/hop-server"
    temp_keys = Path("/tmp/root_authorized_keys")

    try:
        # Copy keys to temp location
        shutil.copy2(root_keys, temp_keys)
        hop3_uid = pwd.getpwnam(HOP3_USER).pw_uid
        hop3_gid = grp.getgrnam(HOP3_GROUP).gr_gid
        os.chown(temp_keys, hop3_uid, hop3_gid)

        # Run setup:ssh
        run_as_hop3(f"{hop_server} setup:ssh {temp_keys}")
        print_success("SSH keys configured")
    except CommandError:
        print_warning("Could not configure SSH keys (invalid format?)")
    finally:
        if temp_keys.exists():
            temp_keys.unlink()


def setup_systemd() -> None:
    """Install and enable systemd services."""
    # Hop3 server service
    service_path = Path("/etc/systemd/system/hop3-server.service")
    service_path.write_text(SYSTEMD_UNIT)

    # uWSGI service
    uwsgi_path = Path("/etc/systemd/system/uwsgi-hop3.service")
    uwsgi_path.write_text(UWSGI_UNIT)

    # Reload and enable
    run_cmd(["systemctl", "daemon-reload"])
    run_cmd(["systemctl", "enable", "hop3-server"], check=False)
    run_cmd(["systemctl", "enable", "uwsgi-hop3"], check=False)
    run_cmd(["systemctl", "start", "hop3-server"], check=False)

    print_success("Systemd services configured")


def setup_nginx(skip: bool) -> None:
    """Configure nginx."""
    if skip:
        print_info("Skipping nginx setup (--skip-nginx)")
        return

    run_cmd(["systemctl", "enable", "nginx"], check=False)
    run_cmd(["systemctl", "start", "nginx"], check=False)
    print_success("Nginx enabled and started")


def setup_postgres(skip: bool, distro: str) -> None:
    """Configure PostgreSQL."""
    if skip:
        print_info("Skipping PostgreSQL setup (--skip-postgres)")
        return

    # Initialize PostgreSQL on Fedora
    if distro == "fedora":
        if not Path("/var/lib/pgsql/data/pg_hba.conf").exists():
            run_cmd(["postgresql-setup", "--initdb"], check=False)

    run_cmd(["systemctl", "enable", "postgresql"], check=False)
    run_cmd(["systemctl", "start", "postgresql"], check=False)

    # Create role and database
    try:
        run_cmd(
            ["su", "-", "postgres", "-c", f"createuser --createdb {HOP3_USER}"],
            check=False,
        )
        run_cmd(
            ["su", "-", "postgres", "-c", f"createdb -O {HOP3_USER} hop3"],
            check=False,
        )
        print_success("PostgreSQL role and database created")
    except CommandError:
        print_info("PostgreSQL role/database may already exist")


def setup_acme(skip: bool) -> None:
    """Install acme.sh for Let's Encrypt."""
    if skip:
        print_info("Skipping ACME setup (--skip-acme)")
        return

    acme_sh = HOME_DIR / ".acme.sh" / "acme.sh"

    if acme_sh.exists():
        print_info("acme.sh already installed")
        return

    with Spinner("Installing acme.sh..."):
        # Download
        run_as_hop3(
            "curl -fsSL https://raw.githubusercontent.com/Neilpang/acme.sh/master/acme.sh -o /tmp/acme.sh"
        )
        # Install (must run from /tmp)
        run_as_hop3("cd /tmp && bash acme.sh --install")
        run_cmd(["rm", "-f", "/tmp/acme.sh"])

    # Set default CA
    if acme_sh.exists():
        run_as_hop3(f"bash {acme_sh} --set-default-ca --server letsencrypt")
        print_success("acme.sh installed and configured")
    else:
        print_warning("acme.sh installation may have failed")


def verify_installation() -> bool:
    """Verify the installation."""
    hop_server = VENV_DIR / "bin" / "hop-server"

    if not hop_server.exists():
        print_error("hop-server not found")
        return False

    # Check service status
    result = run_cmd(["systemctl", "is-active", "hop3-server"], capture=True, check=False)
    if result.stdout.strip() == "active":
        print_success("hop3-server service is running")
    else:
        print_warning("hop3-server service is not running")
        print_detail("Check with: sudo systemctl status hop3-server")

    return True


def print_final_message() -> None:
    """Print success message with next steps."""
    print()
    print(f"{Colors.GREEN}{Colors.BOLD}Installation complete!{Colors.RESET}")
    print()
    print(f"  {Colors.BOLD}User:{Colors.RESET}      {HOP3_USER}")
    print(f"  {Colors.BOLD}Home:{Colors.RESET}      {HOME_DIR}")
    print(f"  {Colors.BOLD}Venv:{Colors.RESET}      {VENV_DIR}")
    print()
    print(f"  {Colors.BOLD}Services:{Colors.RESET}")
    print("    sudo systemctl status hop3-server")
    print("    sudo systemctl status uwsgi-hop3")
    print()
    print(f"  {Colors.BOLD}Next steps:{Colors.RESET}")
    print("    1. Add your SSH key:  ssh-copy-id hop3@your-server")
    print("    2. Deploy an app:     hop3 deploy your-app.git")
    print()
    print(f"  {Colors.BOLD}Logs:{Colors.RESET}")
    print("    sudo journalctl -u hop3-server -f")
    print()


# =============================================================================
# CLI Argument Parsing
# =============================================================================


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="install-server.py",
        description="Install the Hop3 Server. Must be run as root.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  sudo python3 install-server.py                  Install latest from PyPI
  sudo python3 install-server.py --git            Install from git (main branch)
  sudo python3 install-server.py --git --branch x Install from git (x branch)
  sudo python3 install-server.py --skip-postgres  Skip PostgreSQL setup

Environment Variables:
  HOP3_VERSION          Install specific version
  HOP3_GIT              Install from git (1 or true)
  HOP3_BRANCH           Git branch (default: main)
  HOP3_LOCAL_PACKAGE    Install from local path
  HOP3_SKIP_DEPS        Skip system dependencies
  HOP3_SKIP_NGINX       Skip nginx setup
  HOP3_SKIP_POSTGRES    Skip PostgreSQL setup
  HOP3_SKIP_ACME        Skip ACME/Let's Encrypt setup
""",
    )

    parser.add_argument(
        "--version",
        metavar="VERSION",
        default=os.environ.get("HOP3_VERSION"),
        help="Install a specific version (e.g., 0.4.0)",
    )

    parser.add_argument(
        "--git",
        action="store_true",
        default=os.environ.get("HOP3_GIT", "").lower() in ("1", "true"),
        help="Install from git repository",
    )

    parser.add_argument(
        "--branch",
        metavar="BRANCH",
        default=os.environ.get("HOP3_BRANCH", DEFAULT_BRANCH),
        help=f"Git branch to install from (default: {DEFAULT_BRANCH})",
    )

    parser.add_argument(
        "--local-path",
        metavar="PATH",
        default=os.environ.get("HOP3_LOCAL_PACKAGE"),
        help="Install from a local directory",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        default=os.environ.get("HOP3_FORCE", "").lower() in ("1", "true"),
        help="Force reinstall even if already installed",
    )

    parser.add_argument(
        "--skip-deps",
        action="store_true",
        default=os.environ.get("HOP3_SKIP_DEPS", "").lower() in ("1", "true"),
        help="Skip system dependency installation",
    )

    parser.add_argument(
        "--skip-nginx",
        action="store_true",
        default=os.environ.get("HOP3_SKIP_NGINX", "").lower() in ("1", "true"),
        help="Skip nginx setup",
    )

    parser.add_argument(
        "--skip-postgres",
        action="store_true",
        default=os.environ.get("HOP3_SKIP_POSTGRES", "").lower() in ("1", "true"),
        help="Skip PostgreSQL setup",
    )

    parser.add_argument(
        "--skip-acme",
        action="store_true",
        default=os.environ.get("HOP3_SKIP_ACME", "").lower() in ("1", "true"),
        help="Skip ACME/Let's Encrypt setup",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        default=os.environ.get("HOP3_VERBOSE", "").lower() in ("1", "true"),
        help="Show verbose output",
    )

    return parser


# =============================================================================
# Main
# =============================================================================


def main() -> int:
    """Main entry point. Returns exit code."""
    parser = create_parser()
    args = parser.parse_args()

    # Header
    print_header("Hop3 Server Installer")

    # Check root
    if os.geteuid() != 0:
        print_error("This installer must be run as root")
        print_detail("Use: sudo python3 install-server.py")
        return 1

    # Detect distro
    distro = detect_distro()
    print_info(f"Detected distribution: {distro}")

    total_steps = 10

    # Step 1: System dependencies
    print_step(1, total_steps, "Installing system dependencies...")
    try:
        install_system_deps(distro, args.skip_deps)
    except CommandError as e:
        print_error(f"Failed to install dependencies: {e.stderr[:200]}")
        return 1

    # Step 2: Create user
    print_step(2, total_steps, "Creating hop3 user and group...")
    try:
        create_user_and_group()
    except CommandError as e:
        print_error(f"Failed to create user: {e.stderr}")
        return 1

    # Step 3: Virtual environment
    print_step(3, total_steps, "Creating virtual environment...")
    try:
        create_virtual_environment()
    except CommandError as e:
        print_error(f"Failed to create venv: {e.stderr}")
        return 1

    # Step 4: Install package
    print_step(4, total_steps, "Installing hop3-server...")
    try:
        install_package(
            version=args.version,
            use_git=args.git,
            branch=args.branch,
            local_path=args.local_path,
            verbose=args.verbose,
        )
    except CommandError as e:
        print_error("Failed to install hop3-server")
        if args.verbose:
            print_detail(e.stderr[:500])
        return 1

    # Step 5: Run setup
    print_step(5, total_steps, "Running initial setup...")
    try:
        run_hop3_setup()
    except CommandError as e:
        print_error(f"Setup failed: {e.stderr[:200]}")
        return 1

    # Step 6: SSH keys
    print_step(6, total_steps, "Configuring SSH keys...")
    setup_ssh_keys()

    # Step 7: Systemd
    print_step(7, total_steps, "Setting up systemd services...")
    try:
        setup_systemd()
    except CommandError as e:
        print_warning(f"Systemd setup issue: {e.stderr[:100]}")

    # Step 8: Nginx
    print_step(8, total_steps, "Configuring nginx...")
    try:
        setup_nginx(args.skip_nginx)
    except CommandError as e:
        print_warning(f"Nginx setup issue: {e.stderr[:100]}")

    # Step 9: PostgreSQL
    print_step(9, total_steps, "Configuring PostgreSQL...")
    try:
        setup_postgres(args.skip_postgres, distro)
    except CommandError as e:
        print_warning(f"PostgreSQL setup issue: {e.stderr[:100]}")

    # Step 10: ACME
    print_step(10, total_steps, "Setting up ACME/Let's Encrypt...")
    try:
        setup_acme(args.skip_acme)
    except CommandError as e:
        print_warning(f"ACME setup issue: {e.stderr[:100]}")

    # Verify
    print()
    verify_installation()

    # Success
    print_final_message()

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nInstallation cancelled.")
        sys.exit(130)
    except Exception as e:
        print(f"\n{Colors.RED}Error:{Colors.RESET} {e}", file=sys.stderr)
        sys.exit(1)
