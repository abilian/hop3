#!/usr/bin/env python3
# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Hop3 Server Installer.

This script installs the Hop3 Server by:
1. Installing system dependencies
2. Creating the hop3 user and group
3. Creating a virtual environment at /home/hop3/venv
4. Installing the hop3-server package
5. Running initial setup
6. Configuring systemd services
7. Optionally setting up nginx and PostgreSQL

Usage:
    sudo python install-server.py [OPTIONS]

Options:
    --force             Force reinstall even if already installed
    --verbose           Enable verbose output
    --version VERSION   Install a specific version (e.g., 0.4.0)
    --git               Install from git (head of main branch)
    --skip-deps         Skip system dependency installation
    --skip-nginx        Skip nginx setup
    --skip-postgres     Skip PostgreSQL setup
    --help              Show this help message
"""

from __future__ import annotations

import argparse
import grp
import os
import pwd
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

# =============================================================================
# Configuration
# =============================================================================

HOP3_USER = "hop3"
HOP3_GROUP = "hop3"
HOME_DIR = Path("/home") / HOP3_USER
VENV_DIR = HOME_DIR / "venv"

PACKAGE_NAME = "hop3-server"
GIT_URL = (
    "git+https://github.com/abilian/hop3.git@main#subdirectory=packages/hop3-server"
)

# System dependencies by distribution
DEBIAN_PACKAGES = [
    # Basic tools
    "bc",
    "git",
    "sudo",
    "cron",
    "build-essential",
    "pkg-config",
    "libpcre3-dev",
    "zlib1g-dev",
    # Python
    "python3",
    "python3-pip",
    "python3-dev",
    "python3-venv",
    "python3-virtualenv",
    "python3-setuptools",
    "python3-wheel",
    # Libraries needed for Python packages
    "libffi-dev",
    "libssl-dev",
    # Nginx
    "nginx",
    "acl",
    # uWSGI
    "uwsgi-core",
    "uwsgi-plugin-python3",
    # Let's Encrypt
    "certbot",
    # PostgreSQL
    "libpq-dev",
    "postgresql",
    # Language runtimes for builders
    # - Ruby
    "ruby",
    "ruby-dev",
    "ruby-bundler",
    # - Node.js
    "npm",
    "nodeenv",
    # - Go
    "golang",
]

FEDORA_PACKAGES = [
    # Basic tools
    "bc",
    "git",
    "sudo",
    "cronie",
    "gcc",
    "gcc-c++",
    "make",
    "pkg-config",
    "pcre-devel",
    "zlib-devel",
    # Python
    "python3",
    "python3-pip",
    "python3-devel",
    "python3-virtualenv",
    "python3-setuptools",
    "python3-wheel",
    # Libraries
    "libffi-devel",
    "openssl-devel",
    # Nginx
    "nginx",
    "acl",
    # uWSGI
    "uwsgi",
    "uwsgi-plugin-python3",
    # Let's Encrypt
    "certbot",
    # PostgreSQL
    "libpq-devel",
    "postgresql-server",
    "postgresql",
    # Language runtimes
    "ruby",
    "ruby-devel",
    "rubygem-bundler",
    "npm",
    "golang",
]

ARCH_PACKAGES = [
    # Basic tools
    "bc",
    "git",
    "sudo",
    "cronie",
    "base-devel",
    "pkg-config",
    "pcre",
    "zlib",
    # Python
    "python",
    "python-pip",
    "python-virtualenv",
    "python-setuptools",
    "python-wheel",
    # Libraries
    "libffi",
    "openssl",
    # Nginx
    "nginx",
    "acl",
    # uWSGI
    "uwsgi",
    "uwsgi-plugin-python",
    # Let's Encrypt
    "certbot",
    # PostgreSQL
    "postgresql-libs",
    "postgresql",
    # Language runtimes
    "ruby",
    "ruby-bundler",
    "npm",
    "go",
]

# Systemd unit file for the Hop3 server
SYSTEMD_UNIT = """\
[Unit]
Description=Hop3 Server
After=network.target

[Service]
User=hop3
Group=hop3
WorkingDirectory=/home/hop3
ExecStart=/home/hop3/venv/bin/hop-server serve
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""

# Systemd unit file for uWSGI
UWSGI_UNIT = """\
[Unit]
Description=uWSGI Emperor for Hop3
After=network.target

[Service]
User=hop3
Group=hop3
ExecStart=/usr/local/bin/uwsgi-hop3 --emperor /home/hop3/.hop3/uwsgi-enabled --die-on-term
Restart=always
RestartSec=5
KillSignal=SIGQUIT
Type=notify
NotifyAccess=all

[Install]
WantedBy=multi-user.target
"""

# =============================================================================
# Terminal Colors
# =============================================================================


class Colors:
    """ANSI color codes for terminal output."""

    RESET = "\033[0m"
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[0;33m"
    BLUE = "\033[0;34m"
    BOLD = "\033[1m"

    @classmethod
    def disable(cls) -> None:
        """Disable colors (for non-TTY output)."""
        cls.RESET = ""
        cls.RED = ""
        cls.GREEN = ""
        cls.YELLOW = ""
        cls.BLUE = ""
        cls.BOLD = ""


# Disable colors if not a TTY
if not sys.stdout.isatty():
    Colors.disable()


# =============================================================================
# Logging Functions
# =============================================================================

VERBOSE = False


def log_info(message: str) -> None:
    """Print an info message."""
    print(f"{Colors.BLUE}[INFO]{Colors.RESET} {message}")


def log_success(message: str) -> None:
    """Print a success message."""
    print(f"{Colors.GREEN}[OK]{Colors.RESET} {message}")


def log_warning(message: str) -> None:
    """Print a warning message."""
    print(f"{Colors.YELLOW}[WARN]{Colors.RESET} {message}")


def log_error(message: str) -> None:
    """Print an error message to stderr."""
    print(f"{Colors.RED}[ERROR]{Colors.RESET} {message}", file=sys.stderr)


def log_debug(message: str) -> None:
    """Print a debug message (only in verbose mode)."""
    if VERBOSE:
        print(f"{Colors.BLUE}[DEBUG]{Colors.RESET} {message}")


# =============================================================================
# Utility Functions
# =============================================================================


def run_command(
    cmd: list[str],
    check: bool = True,
    capture_output: bool = False,
    env: dict | None = None,
    user: str | None = None,
) -> subprocess.CompletedProcess:
    """Run a command and handle errors."""
    if user:
        cmd = ["su", "-", user, "-c", " ".join(cmd)]

    log_debug(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            check=check,
            capture_output=capture_output,
            text=True,
            env=env,
        )
        return result
    except subprocess.CalledProcessError as e:
        log_error(f"Command failed: {' '.join(cmd)}")
        if e.stdout:
            log_error(f"stdout: {e.stdout}")
        if e.stderr:
            log_error(f"stderr: {e.stderr}")
        raise


def run_as_hop3(cmd: str) -> subprocess.CompletedProcess:
    """Run a command as the hop3 user."""
    return run_command(["su", "-", HOP3_USER, "-c", cmd])


def detect_distro() -> str:
    """Detect the Linux distribution."""
    # Check /etc/os-release
    os_release = Path("/etc/os-release")
    if os_release.exists():
        content = os_release.read_text()
        if "debian" in content.lower() or "ubuntu" in content.lower():
            return "debian"
        if (
            "fedora" in content.lower()
            or "rhel" in content.lower()
            or "centos" in content.lower()
        ):
            return "fedora"
        if "arch" in content.lower():
            return "arch"

    # Fallback to checking package managers
    if shutil.which("apt"):
        return "debian"
    if shutil.which("dnf"):
        return "fedora"
    if shutil.which("pacman"):
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


def check_root() -> None:
    """Check if running as root."""
    if os.geteuid() != 0:
        log_error("This installer must be run as root.")
        log_error("Please run with sudo:")
        log_error("  sudo python install-server.py")
        sys.exit(1)


def check_existing_installation(force: bool) -> bool:
    """Check if Hop3 Server is already installed.

    Returns True if we should proceed with installation.
    """
    hop_server_bin = VENV_DIR / "bin" / "hop-server"
    if hop_server_bin.exists():
        if force:
            log_info("Existing installation found. Forcing reinstall...")
            return True
        log_warning("Hop3 Server is already installed.")
        log_info("Use --force to reinstall.")
        return False
    return True


def install_system_dependencies(skip: bool) -> None:
    """Install system dependencies using the appropriate package manager."""
    if skip:
        log_info("Skipping system dependency installation (--skip-deps).")
        return

    distro = detect_distro()
    log_info(f"Detected distribution: {distro}")

    if distro == "debian":
        log_info("Installing Debian/Ubuntu packages...")
        run_command(["apt", "update"], capture_output=not VERBOSE)
        run_command(
            ["apt", "install", "-y"] + DEBIAN_PACKAGES,
            capture_output=not VERBOSE,
        )
    elif distro == "fedora":
        log_info("Installing Fedora/RHEL packages...")
        run_command(
            ["dnf", "install", "-y"] + FEDORA_PACKAGES,
            capture_output=not VERBOSE,
        )
    elif distro == "arch":
        log_info("Installing Arch Linux packages...")
        run_command(
            ["pacman", "-Sy", "--noconfirm"] + ARCH_PACKAGES,
            capture_output=not VERBOSE,
        )
    else:
        log_warning(f"Unknown distribution: {distro}")
        log_warning("Skipping automatic dependency installation.")
        log_warning("Please install the required packages manually.")
        return

    log_success("System dependencies installed.")


def create_hop3_user() -> None:
    """Create the hop3 user and group."""
    # Create group if it doesn't exist
    if not group_exists(HOP3_GROUP):
        log_info(f"Creating group: {HOP3_GROUP}")
        run_command(["groupadd", HOP3_GROUP])
    else:
        log_debug(f"Group {HOP3_GROUP} already exists.")

    # Create user if it doesn't exist
    if not user_exists(HOP3_USER):
        log_info(f"Creating user: {HOP3_USER}")
        run_command([
            "useradd",
            "-m",
            "-g",
            HOP3_GROUP,
            "-s",
            "/bin/bash",
            "-d",
            str(HOME_DIR),
            HOP3_USER,
        ])
    else:
        log_debug(f"User {HOP3_USER} already exists.")

    # Add www-data to hop3 group (for nginx socket access)
    if user_exists("www-data"):
        log_info("Adding www-data to hop3 group...")
        run_command(["usermod", "-a", "-G", HOP3_GROUP, "www-data"])

    log_success("User and group configured.")


def create_virtual_environment() -> None:
    """Create a Python virtual environment for hop3."""
    log_info(f"Creating virtual environment: {VENV_DIR}")

    if VENV_DIR.exists():
        log_debug("Removing existing virtual environment...")
        shutil.rmtree(VENV_DIR)

    # Create venv as hop3 user
    run_as_hop3(f"python3 -m venv {VENV_DIR}")

    log_success("Virtual environment created.")


def install_hop3_server(version: str | None, use_git: bool) -> None:
    """Install the hop3-server package into the virtual environment."""
    pip_path = VENV_DIR / "bin" / "pip"

    # Upgrade pip first
    log_info("Upgrading pip...")
    run_as_hop3(f"{pip_path} install --upgrade pip")

    # Determine what to install
    if use_git:
        log_info("Installing hop3-server from git (main branch)...")
        package_spec = GIT_URL
    elif version:
        log_info(f"Installing hop3-server version {version}...")
        package_spec = f"{PACKAGE_NAME}=={version}"
    else:
        log_info("Installing hop3-server (latest version)...")
        package_spec = PACKAGE_NAME

    # Install the package
    try:
        run_as_hop3(f"{pip_path} install '{package_spec}'")
    except subprocess.CalledProcessError:
        log_error("Failed to install hop3-server.")
        if use_git:
            log_error("Make sure git is installed and you have network access.")
        else:
            log_error("The package may not be available on PyPI yet.")
            log_error("Try using --git to install from the git repository.")
        sys.exit(1)

    log_success("hop3-server installed successfully.")


def run_hop3_setup() -> None:
    """Run hop3 setup to initialize directories and configuration."""
    log_info("Running hop3 setup...")

    hop_server = VENV_DIR / "bin" / "hop-server"
    run_as_hop3(f"{hop_server} setup")

    log_success("Hop3 setup complete.")


def setup_ssh_keys() -> None:
    """Copy root's SSH authorized_keys to hop3 user."""
    log_info("Setting up SSH keys...")

    root_keys = Path("/root/.ssh/authorized_keys")
    if root_keys.exists():
        hop_server = VENV_DIR / "bin" / "hop-server"

        # Copy keys to temp location
        temp_keys = Path("/tmp/root_authorized_keys")
        shutil.copy2(root_keys, temp_keys)
        os.chown(
            temp_keys, pwd.getpwnam(HOP3_USER).pw_uid, grp.getgrnam(HOP3_GROUP).gr_gid
        )

        # Run setup:ssh
        run_as_hop3(f"{hop_server} setup:ssh {temp_keys}")

        # Clean up
        temp_keys.unlink()

        log_success("SSH keys configured.")
    else:
        log_warning("No root SSH keys found. Skipping SSH setup.")
        log_warning("You'll need to add SSH keys manually later.")


def setup_systemd_services() -> None:
    """Install and enable systemd services."""
    log_info("Setting up systemd services...")

    # Hop3 server service
    service_path = Path("/etc/systemd/system/hop3-server.service")
    service_path.write_text(SYSTEMD_UNIT)
    log_debug(f"Created {service_path}")

    # uWSGI service
    uwsgi_service_path = Path("/etc/systemd/system/uwsgi-hop3.service")
    uwsgi_service_path.write_text(UWSGI_UNIT)
    log_debug(f"Created {uwsgi_service_path}")

    # Create uwsgi symlink
    uwsgi_bin = Path("/usr/local/bin/uwsgi-hop3")
    if not uwsgi_bin.exists():
        uwsgi_source = Path("/usr/bin/uwsgi")
        if uwsgi_source.exists():
            uwsgi_bin.symlink_to(uwsgi_source)

    # Reload systemd
    run_command(["systemctl", "daemon-reload"])

    # Enable and start hop3-server
    run_command(["systemctl", "enable", "hop3-server"])
    run_command(["systemctl", "start", "hop3-server"])

    # Enable uwsgi-hop3 (don't start yet, no apps)
    run_command(["systemctl", "enable", "uwsgi-hop3"])

    log_success("Systemd services configured.")


def setup_nginx(skip: bool) -> None:
    """Configure nginx as reverse proxy."""
    if skip:
        log_info("Skipping nginx setup (--skip-nginx).")
        return

    log_info("Setting up nginx...")

    # Restart nginx to pick up any changes
    run_command(["systemctl", "enable", "nginx"])
    run_command(["systemctl", "restart", "nginx"])

    log_success("Nginx configured.")


def setup_postgres(skip: bool) -> None:
    """Set up PostgreSQL database and user."""
    if skip:
        log_info("Skipping PostgreSQL setup (--skip-postgres).")
        return

    log_info("Setting up PostgreSQL...")

    distro = detect_distro()

    # Initialize PostgreSQL on Fedora/RHEL if needed
    if distro == "fedora":
        data_dir = Path("/var/lib/pgsql/data")
        if not data_dir.exists() or not any(data_dir.iterdir()):
            log_info("Initializing PostgreSQL database...")
            run_command(["postgresql-setup", "--initdb"], check=False)

    # Start and enable PostgreSQL
    run_command(["systemctl", "enable", "postgresql"])
    run_command(["systemctl", "start", "postgresql"])

    # Generate secure password
    db_password = secrets.token_urlsafe(32)

    # Store password in secure file
    password_file = HOME_DIR / ".hop3_postgres_password"
    password_file.write_text(db_password)
    os.chmod(password_file, 0o600)
    os.chown(
        password_file, pwd.getpwnam(HOP3_USER).pw_uid, grp.getgrnam(HOP3_GROUP).gr_gid
    )

    # Create PostgreSQL role and database
    try:
        # Check if role exists
        result = run_command(
            [
                "su",
                "-",
                "postgres",
                "-c",
                f"psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='{HOP3_USER}'\"",
            ],
            capture_output=True,
            check=False,
        )

        if "1" not in (result.stdout or ""):
            log_info("Creating PostgreSQL role...")
            run_command([
                "su",
                "-",
                "postgres",
                "-c",
                f"psql -c \"CREATE ROLE {HOP3_USER} WITH LOGIN SUPERUSER PASSWORD '{db_password}'\"",
            ])

        # Check if database exists
        result = run_command(
            [
                "su",
                "-",
                "postgres",
                "-c",
                f"psql -tAc \"SELECT 1 FROM pg_database WHERE datname='{HOP3_USER}'\"",
            ],
            capture_output=True,
            check=False,
        )

        if "1" not in (result.stdout or ""):
            log_info("Creating PostgreSQL database...")
            run_command([
                "su",
                "-",
                "postgres",
                "-c",
                f'psql -c "CREATE DATABASE {HOP3_USER} OWNER {HOP3_USER}"',
            ])

    except subprocess.CalledProcessError as e:
        log_warning(f"PostgreSQL setup encountered an error: {e}")
        log_warning("You may need to configure PostgreSQL manually.")

    log_success("PostgreSQL configured.")


def setup_acme() -> None:
    """Install acme.sh for Let's Encrypt certificates."""
    log_info("Setting up ACME/Let's Encrypt...")

    acme_sh = HOME_DIR / ".acme.sh" / "acme.sh"
    if acme_sh.exists():
        log_debug("acme.sh already installed, upgrading...")
        run_as_hop3(f"bash {acme_sh} --upgrade")
    else:
        log_info("Installing acme.sh...")
        # Download and install
        run_as_hop3(
            "curl -fsSL https://raw.githubusercontent.com/Neilpang/acme.sh/master/acme.sh -o /tmp/acme.sh"
        )
        run_as_hop3("bash /tmp/acme.sh --install")
        run_as_hop3("rm /tmp/acme.sh")

    # Set default CA to Let's Encrypt
    run_as_hop3(
        f"bash {HOME_DIR}/.acme.sh/acme.sh --set-default-ca --server letsencrypt"
    )

    log_success("ACME/Let's Encrypt configured.")


def verify_installation() -> bool:
    """Verify that the installation was successful."""
    log_info("Verifying installation...")

    hop_server = VENV_DIR / "bin" / "hop-server"
    if not hop_server.exists():
        log_error("hop-server command not found in virtual environment.")
        return False

    # Check if service is running
    result = run_command(
        ["systemctl", "is-active", "hop3-server"],
        capture_output=True,
        check=False,
    )

    if result.stdout.strip() == "active":
        log_success("Hop3 server is running.")
        return True
    log_warning("Hop3 server service is not running.")
    log_warning("Check with: sudo systemctl status hop3-server")
    return True  # Still consider installation successful


def print_success_message() -> None:
    """Print success message with next steps."""
    print()
    print(
        f"{Colors.GREEN}{Colors.BOLD}Hop3 Server installed successfully!{Colors.RESET}"
    )
    print()
    print("Installation locations:")
    print(f"  - Home directory: {HOME_DIR}")
    print(f"  - Virtual environment: {VENV_DIR}")
    print(f"  - Server binary: {VENV_DIR}/bin/hop-server")
    print()
    print("Services:")
    print("  - hop3-server.service  (main server)")
    print("  - uwsgi-hop3.service   (uWSGI emperor)")
    print()
    print("Useful commands:")
    print("  sudo systemctl status hop3-server    Check server status")
    print("  sudo systemctl restart hop3-server   Restart server")
    print("  sudo journalctl -u hop3-server -f    View server logs")
    print()
    print("Next steps:")
    print("  1. Configure your domain's DNS to point to this server")
    print("  2. Add SSH keys for users who will deploy apps")
    print("  3. Deploy your first app!")
    print()


def print_uninstall_instructions() -> None:
    """Print uninstall instructions."""
    print(f"{Colors.BOLD}To uninstall Hop3 Server:{Colors.RESET}")
    print("  sudo systemctl stop hop3-server uwsgi-hop3")
    print("  sudo systemctl disable hop3-server uwsgi-hop3")
    print("  sudo userdel -r hop3")
    print("  sudo rm -f /etc/systemd/system/hop3-server.service")
    print("  sudo rm -f /etc/systemd/system/uwsgi-hop3.service")
    print("  sudo systemctl daemon-reload")
    print("  # Optionally remove nginx configs and PostgreSQL database")
    print()


# =============================================================================
# Argument Parsing
# =============================================================================


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Install the Hop3 Server.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  sudo python install-server.py                    Install latest version
  sudo python install-server.py --git              Install from git (main branch)
  sudo python install-server.py --version 0.4.0   Install specific version
  sudo python install-server.py --skip-postgres   Skip PostgreSQL setup
        """,
    )

    parser.add_argument(
        "--force",
        action="store_true",
        default=os.environ.get("HOP3_FORCE_REINSTALL", "").lower() in ("1", "true"),
        help="Force reinstall even if already installed",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        default=os.environ.get("HOP3_VERBOSE", "").lower() in ("1", "true"),
        help="Enable verbose output",
    )

    parser.add_argument(
        "--version",
        type=str,
        default=os.environ.get("HOP3_VERSION"),
        help="Install a specific version (e.g., 0.4.0)",
    )

    parser.add_argument(
        "--git",
        action="store_true",
        default=os.environ.get("HOP3_GIT", "").lower() in ("1", "true"),
        help="Install from git (head of main branch)",
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

    return parser.parse_args()


# =============================================================================
# Main
# =============================================================================


def main() -> None:
    """Main entry point."""
    global VERBOSE

    args = parse_arguments()
    VERBOSE = args.verbose

    print()
    print(f"{Colors.BOLD}Hop3 Server Installer{Colors.RESET}")
    print("=" * 40)
    print()

    # Pre-flight checks
    check_root()

    if not check_existing_installation(args.force):
        sys.exit(0)

    # Run installation steps
    install_system_dependencies(args.skip_deps)
    create_hop3_user()
    create_virtual_environment()
    install_hop3_server(args.version, args.git)
    run_hop3_setup()
    setup_ssh_keys()
    setup_systemd_services()
    setup_nginx(args.skip_nginx)
    setup_postgres(args.skip_postgres)
    setup_acme()

    # Verify and report
    verify_installation()

    print_success_message()
    print_uninstall_instructions()


if __name__ == "__main__":
    main()
