# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Hop3 Server Installer.

A single-file installer for the Hop3 Server.
Uses only Python standard library for maximum portability.
Must be run as root.

Usage:
    curl -LsSf https://hop3.cloud/install-server.py | sudo python3 -
    curl -LsSf https://hop3.cloud/install-server.py | sudo python3 - --git
    sudo python3 install-server.py --help
"""

from __future__ import annotations

import argparse
import grp
import os
import pwd
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from ..common import (
    Colors,
    CommandError,
    Spinner,
    check_python_version,
    cmd_exists,
    detect_distro,
    print_detail,
    print_error,
    print_header,
    print_info,
    print_step,
    print_success,
    print_warning,
    run_cmd,
)
from .config import (
    DEBIAN_DOCKER_PACKAGES,
    DEBIAN_MYSQL_PACKAGES,
    DEBIAN_PACKAGES,
    DEBIAN_REDIS_PACKAGES,
    DEFAULT_BRANCH,
    FEDORA_DOCKER_PACKAGES,
    FEDORA_MYSQL_PACKAGES,
    FEDORA_PACKAGES,
    FEDORA_REDIS_PACKAGES,
    GIT_REPO,
    GIT_SUBDIR,
    HOME_DIR,
    HOP3_GROUP,
    HOP3_USER,
    NGINX_CONFIG,
    PACKAGE_NAME,
    SSL_CERT,
    SSL_DIR,
    SSL_KEY,
    SUDOERS_CONTENT,
    SYSTEMD_UNIT,
    UWSGI_UNIT,
    VENV_DIR,
    ServerInstallerConfig,
    parse_features,
)

# =============================================================================
# User/Group Management
# =============================================================================


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


def run_as_hop3(cmd: str) -> subprocess.CompletedProcess:
    """Run a command as the hop3 user."""
    return run_cmd(["su", "-", HOP3_USER, "-c", cmd])


# =============================================================================
# System Dependencies
# =============================================================================


def install_system_deps(distro: str, config: ServerInstallerConfig) -> None:
    """Install system dependencies."""
    if config.skip_deps:
        print_info("Skipping system dependencies (--skip-deps)")
        return

    if distro == "debian":
        _install_debian_deps(config)
    elif distro == "fedora":
        _install_fedora_deps(config)
    else:
        print_warning(f"Unknown distro '{distro}', skipping package installation")
        print_detail("You may need to install dependencies manually")


def _install_debian_deps(config: ServerInstallerConfig) -> None:
    """Install Debian/Ubuntu dependencies."""
    with Spinner("Updating package lists..."):
        run_cmd(["apt-get", "update", "-q"])

    with Spinner("Installing base packages (this may take a while)..."):
        result = run_cmd(
            ["apt-get", "install", "-y"] + DEBIAN_PACKAGES,
            env={"DEBIAN_FRONTEND": "noninteractive"},
            check=False,
        )

    if result.returncode != 0:
        print_error("Base package installation failed")
        if result.stderr:
            for line in result.stderr.strip().split("\n")[-10:]:
                print_detail(line)
        raise CommandError(
            ["apt-get", "install"] + DEBIAN_PACKAGES,
            result.returncode,
            result.stderr or "",
        )

    print_success(f"Installed {len(DEBIAN_PACKAGES)} base packages")

    # Handle npm separately
    if not cmd_exists("npm"):
        print_info("npm not found, installing from Ubuntu repos...")
        with Spinner("Installing npm..."):
            result = run_cmd(
                ["apt-get", "install", "-y", "npm"],
                env={"DEBIAN_FRONTEND": "noninteractive"},
                check=False,
            )
        if result.returncode == 0:
            print_success("npm installed")
        else:
            print_warning("npm installation failed (may conflict with NodeSource)")
    else:
        print_success("npm already available")

    # Optional packages
    if config.with_docker:
        _install_optional_packages(
            "Docker", DEBIAN_DOCKER_PACKAGES, "apt-get", "DEBIAN_FRONTEND"
        )

    if config.with_mysql:
        if not cmd_exists("mysql"):
            _install_optional_packages(
                "MySQL", DEBIAN_MYSQL_PACKAGES, "apt-get", "DEBIAN_FRONTEND"
            )
        else:
            print_success("MySQL already installed")

    if config.with_redis:
        if not cmd_exists("redis-server"):
            _install_optional_packages(
                "Redis", DEBIAN_REDIS_PACKAGES, "apt-get", "DEBIAN_FRONTEND"
            )
        else:
            print_success("Redis already installed")
        _configure_redis()

    # Install .NET SDK (requires Microsoft repo)
    _install_dotnet_sdk("debian")

    # Install Rust toolchain (via rustup)
    _install_rust_toolchain()


def _install_fedora_deps(config: ServerInstallerConfig) -> None:
    """Install Fedora/RHEL dependencies."""
    with Spinner("Installing base packages (this may take a while)..."):
        result = run_cmd(["dnf", "install", "-y"] + FEDORA_PACKAGES, check=False)

    if result.returncode != 0:
        print_error("Base package installation failed")
        if result.stderr:
            for line in result.stderr.strip().split("\n")[-10:]:
                print_detail(line)
        raise CommandError(
            ["dnf", "install"] + FEDORA_PACKAGES,
            result.returncode,
            result.stderr or "",
        )

    print_success(f"Installed {len(FEDORA_PACKAGES)} base packages")

    # Handle npm separately
    if not cmd_exists("npm"):
        with Spinner("Installing npm..."):
            result = run_cmd(["dnf", "install", "-y", "npm"], check=False)
        if result.returncode == 0:
            print_success("npm installed")
        else:
            print_warning("npm installation failed")
    else:
        print_success("npm already available")

    # Optional packages
    if config.with_docker:
        _install_optional_packages("Docker", FEDORA_DOCKER_PACKAGES, "dnf", None)

    if config.with_mysql:
        if not cmd_exists("mysql"):
            _install_optional_packages("MySQL", FEDORA_MYSQL_PACKAGES, "dnf", None)
        else:
            print_success("MySQL already installed")

    if config.with_redis:
        if not cmd_exists("redis-server"):
            _install_optional_packages("Redis", FEDORA_REDIS_PACKAGES, "dnf", None)
        else:
            print_success("Redis already installed")
        _configure_redis()

    # Install .NET SDK
    _install_dotnet_sdk("fedora")

    # Install Rust toolchain (via rustup)
    _install_rust_toolchain()


def _install_optional_packages(
    name: str,
    packages: list[str],
    pkg_manager: str,
    env_var: str | None,
) -> None:
    """Install optional packages."""
    with Spinner(f"Installing {name} packages..."):
        env = {env_var: "noninteractive"} if env_var else None
        result = run_cmd(
            [pkg_manager, "install", "-y"] + packages,
            env=env,
            check=False,
        )
    if result.returncode == 0:
        print_success(f"{name} packages installed")
    else:
        print_warning(f"{name} installation failed")
        if result.stderr:
            for line in result.stderr.strip().split("\n")[-5:]:
                print_detail(line)


def _configure_redis() -> None:
    """Configure Redis for Hop3 use.

    Ensures Redis is:
    - Running as a primary (not a replica)
    - Enabled and started
    - Accessible on localhost
    """
    print_info("Configuring Redis...")

    # Ensure Redis is not configured as a replica
    # This fixes the "You can't write against a read only replica" error
    result = run_cmd(
        ["redis-cli", "CONFIG", "SET", "replica-read-only", "no"],
        check=False,
    )
    if result.returncode != 0:
        print_warning(
            "Could not set replica-read-only=no (Redis may not be running yet)"
        )

    # Remove any replicaof configuration (make this a primary)
    result = run_cmd(
        ["redis-cli", "REPLICAOF", "NO", "ONE"],
        check=False,
    )
    if result.returncode == 0:
        print_detail("Redis configured as primary (not replica)")

    # Enable and start Redis service
    run_cmd(["systemctl", "enable", "redis-server"], check=False)
    run_cmd(["systemctl", "start", "redis-server"], check=False)

    # Verify Redis is working
    result = run_cmd(["redis-cli", "PING"], check=False)
    if result.returncode == 0 and "PONG" in result.stdout:
        print_success("Redis configured and running")
    else:
        print_warning("Redis may not be running correctly")


def _install_rust_toolchain() -> None:
    """Install Rust toolchain via rustup.

    Rust is installed using rustup, which manages the Rust toolchain.
    This is installed for the hop3 user so apps can be built.
    Symlinks are created in /usr/local/bin for system-wide access.
    """
    cargo_path = HOME_DIR / ".cargo" / "bin" / "cargo"
    rustc_path = HOME_DIR / ".cargo" / "bin" / "rustc"
    rustup_path = HOME_DIR / ".cargo" / "bin" / "rustup"

    # Check if cargo actually works for the hop3 user
    if cargo_path.exists():
        result = run_as_hop3(f"{cargo_path} --version")
        if result.returncode == 0:
            print_info(f"Rust toolchain already installed: {result.stdout.strip()}")
            # Ensure symlinks exist
            _create_rust_symlinks(cargo_path, rustc_path, rustup_path)
            return

    print_info("Installing Rust toolchain via rustup...")

    # Remove any broken symlinks first
    for symlink in [
        "/usr/local/bin/cargo",
        "/usr/local/bin/rustc",
        "/usr/local/bin/rustup",
    ]:
        symlink_path = Path(symlink)
        if symlink_path.is_symlink() and not symlink_path.exists():
            print_detail(f"Removing broken symlink: {symlink}")
            symlink_path.unlink()

    # Install rustup for the hop3 user
    with Spinner("Downloading and installing rustup..."):
        result = run_as_hop3(
            'curl --proto "=https" --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y'
        )

    if result.returncode != 0:
        print_warning("Rust installation failed")
        if result.stderr:
            print_detail(result.stderr[:200])
        return

    # Verify installation
    if cargo_path.exists():
        print_success("Rust toolchain installed")
        # Show version
        result = run_as_hop3(f"{cargo_path} --version")
        if result.returncode == 0:
            print_detail(f"Version: {result.stdout.strip()}")

        # Create system-wide symlinks
        _create_rust_symlinks(cargo_path, rustc_path, rustup_path)
    else:
        print_warning("Rust installation completed but cargo not found")


def _create_rust_symlinks(
    cargo_path: Path, rustc_path: Path, rustup_path: Path
) -> None:
    """Create symlinks in /usr/local/bin for Rust tools.

    This makes cargo, rustc, and rustup accessible system-wide,
    which is needed when subprocess runs commands without the hop3 user's PATH.
    """
    symlinks = [
        (cargo_path, Path("/usr/local/bin/cargo")),
        (rustc_path, Path("/usr/local/bin/rustc")),
        (rustup_path, Path("/usr/local/bin/rustup")),
    ]

    for source, target in symlinks:
        if not source.exists():
            continue

        # Remove existing symlink or file
        if target.exists() or target.is_symlink():
            target.unlink()

        try:
            target.symlink_to(source)
            print_detail(f"Created symlink: {target} -> {source}")
        except OSError as e:
            print_warning(f"Could not create symlink {target}: {e}")


def _install_dotnet_sdk(distro: str) -> None:
    """Install .NET SDK from Microsoft repository.

    .NET requires adding Microsoft's package repository before installation.
    This installs .NET 8 (LTS) and .NET 9 SDKs.
    """
    if cmd_exists("dotnet"):
        print_info(".NET SDK already installed")
        return

    if distro == "debian":
        # Add Microsoft package repository for Debian/Ubuntu
        with Spinner("Adding Microsoft package repository..."):
            # Download and install the Microsoft package signing key
            run_cmd(
                [
                    "wget",
                    "-q",
                    "https://packages.microsoft.com/config/ubuntu/24.04/packages-microsoft-prod.deb",
                    "-O",
                    "/tmp/packages-microsoft-prod.deb",
                ],
                check=False,
            )
            result = run_cmd(
                ["dpkg", "-i", "/tmp/packages-microsoft-prod.deb"],
                check=False,
            )
            run_cmd(["rm", "-f", "/tmp/packages-microsoft-prod.deb"], check=False)

            if result.returncode != 0:
                print_warning("Failed to add Microsoft repository")
                return

        # Update package lists
        with Spinner("Updating package lists..."):
            run_cmd(["apt-get", "update", "-q"], check=False)

        # Install .NET SDKs
        with Spinner("Installing .NET SDK 8 (LTS)..."):
            result = run_cmd(
                ["apt-get", "install", "-y", "dotnet-sdk-8.0"],
                env={"DEBIAN_FRONTEND": "noninteractive"},
                check=False,
            )
            if result.returncode == 0:
                print_success(".NET SDK 8 installed")
            else:
                print_warning(".NET SDK 8 installation failed")

        with Spinner("Installing .NET SDK 9..."):
            result = run_cmd(
                ["apt-get", "install", "-y", "dotnet-sdk-9.0"],
                env={"DEBIAN_FRONTEND": "noninteractive"},
                check=False,
            )
            if result.returncode == 0:
                print_success(".NET SDK 9 installed")
            else:
                print_warning(".NET SDK 9 installation failed")

    elif distro == "fedora":
        # Fedora has .NET in its repos
        with Spinner("Installing .NET SDK..."):
            result = run_cmd(
                ["dnf", "install", "-y", "dotnet-sdk-8.0", "dotnet-sdk-9.0"],
                check=False,
            )
            if result.returncode == 0:
                print_success(".NET SDK installed")
            else:
                print_warning(".NET SDK installation failed")
    else:
        print_warning(f"Skipping .NET SDK for unsupported distro: {distro}")


# =============================================================================
# User Setup
# =============================================================================


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
        run_cmd(
            [
                "useradd",
                "-m",
                "-g",
                HOP3_GROUP,
                "-s",
                "/bin/bash",
                "-d",
                str(HOME_DIR),
                HOP3_USER,
            ]
        )
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


# =============================================================================
# Virtual Environment and Package Installation
# =============================================================================


def create_virtual_environment() -> None:
    """Create Python virtual environment."""
    if VENV_DIR.exists():
        shutil.rmtree(VENV_DIR)

    with Spinner("Creating virtual environment..."):
        run_as_hop3(f"python3 -m venv {VENV_DIR}")

    print_success(f"Virtual environment created at {VENV_DIR}")


def install_package(config: ServerInstallerConfig) -> None:
    """Install the hop3-server package."""
    pip = f"{VENV_DIR}/bin/pip"

    # Upgrade pip
    with Spinner("Upgrading pip..."):
        run_as_hop3(f"{pip} install --upgrade pip")

    # Determine what to install
    # Note: All user-controlled package specs are quoted to prevent command injection
    if config.local_path:
        package_spec = config.local_path
        source_desc = f"local path ({config.local_path})"
    elif config.use_git:
        with Spinner("Installing build tools..."):
            run_as_hop3(f"{pip} install uv")
        package_spec = f"git+{GIT_REPO}@{config.branch}#subdirectory={GIT_SUBDIR}"
        source_desc = f"git ({config.branch} branch)"
    elif config.version:
        package_spec = f"{PACKAGE_NAME}=={config.version}"
        source_desc = f"PyPI (version {config.version})"
    else:
        package_spec = PACKAGE_NAME
        source_desc = "PyPI (latest)"

    # Install - use shlex.quote to prevent command injection from user-provided values
    with Spinner(f"Installing hop3-server from {source_desc}..."):
        run_as_hop3(f"{pip} install {shlex.quote(package_spec)}")

    print_success("hop3-server installed successfully")


def run_hop3_setup() -> None:
    """Run hop3 setup command."""
    hop_server = f"{VENV_DIR}/bin/hop3-server"

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

    hop_server = f"{VENV_DIR}/bin/hop3-server"

    # Use secure temp file instead of predictable path
    fd, temp_path = tempfile.mkstemp(prefix="hop3_ssh_keys_", suffix=".txt")
    temp_keys = Path(temp_path)

    try:
        # Write keys to secure temp file
        os.close(fd)  # Close the file descriptor, we'll write via shutil
        shutil.copy2(root_keys, temp_keys)

        # Set ownership so hop3 user can read it
        hop3_uid = pwd.getpwnam(HOP3_USER).pw_uid
        hop3_gid = grp.getgrnam(HOP3_GROUP).gr_gid
        os.chown(temp_keys, hop3_uid, hop3_gid)
        os.chmod(temp_keys, 0o600)  # Restrict permissions

        # Run setup:ssh - quote the path for safety
        run_as_hop3(f"{hop_server} setup:ssh {shlex.quote(str(temp_keys))}")
        print_success("SSH keys configured")
    except CommandError:
        print_warning("Could not configure SSH keys (invalid format?)")
    finally:
        if temp_keys.exists():
            temp_keys.unlink()


# =============================================================================
# Systemd Services
# =============================================================================


def setup_environment_file() -> str:
    """Create /etc/default/hop3 with required environment variables.

    Returns:
        The secret key (either existing or newly generated)
    """
    env_file = Path("/etc/default/hop3")

    # Check if file already exists and has HOP3_SECRET_KEY
    if env_file.exists():
        content = env_file.read_text()
        for line in content.splitlines():
            if line.startswith("HOP3_SECRET_KEY="):
                return line.split("=", 1)[1].strip()

    # Generate a secure secret key
    secret_key = secrets.token_urlsafe(32)

    # Write the environment file
    env_content = f"""# Hop3 Server Environment Variables
# This file is loaded by the hop3-server systemd service

# Secret key for JWT token signing (required for authentication)
HOP3_SECRET_KEY={secret_key}
"""
    env_file.write_text(env_content)
    env_file.chmod(0o600)  # Restrict permissions

    return secret_key


def setup_systemd() -> str:
    """Install and enable systemd services.

    Returns:
        The secret key from the environment file
    """
    # Create environment file first
    secret_key = setup_environment_file()

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
    run_cmd(["systemctl", "start", "uwsgi-hop3"], check=False)

    print_success("Systemd services configured")

    return secret_key


# =============================================================================
# SSL Certificates
# =============================================================================


def setup_ssl_selfsigned() -> None:
    """Generate a self-signed SSL certificate."""
    if SSL_CERT.exists() and SSL_KEY.exists():
        print_info("SSL certificates already exist")
        return

    # Create SSL directory
    SSL_DIR.mkdir(parents=True, exist_ok=True)

    with Spinner("Generating self-signed SSL certificate..."):
        run_cmd(
            [
                "openssl",
                "req",
                "-x509",
                "-nodes",
                "-days",
                "3650",
                "-newkey",
                "rsa:2048",
                "-keyout",
                str(SSL_KEY),
                "-out",
                str(SSL_CERT),
                "-subj",
                "/CN=hop3-server/O=Hop3/C=US",
                "-addext",
                "subjectAltName=DNS:localhost,IP:127.0.0.1",
            ]
        )

    os.chmod(SSL_KEY, 0o600)
    os.chmod(SSL_CERT, 0o644)

    print_success("Self-signed SSL certificate generated")
    print_detail(f"Certificate: {SSL_CERT}")
    print_detail(f"Private key: {SSL_KEY}")


# =============================================================================
# Nginx Configuration
# =============================================================================


def setup_nginx(config: ServerInstallerConfig) -> None:
    """Configure nginx as reverse proxy."""
    if config.skip_nginx:
        print_info("Skipping nginx setup (--skip-nginx)")
        return

    # Determine server name
    server_name = config.domain if config.domain else "_"

    # Generate nginx config
    nginx_config = NGINX_CONFIG.format(
        server_name=server_name,
        ssl_cert=str(SSL_CERT),
        ssl_key=str(SSL_KEY),
    )

    # Write config file
    nginx_config_path = Path("/etc/nginx/sites-available/hop3")
    nginx_enabled_path: Path | None = Path("/etc/nginx/sites-enabled/hop3")

    # For Fedora/RHEL, use conf.d instead
    if not Path("/etc/nginx/sites-available").exists():
        nginx_config_path = Path("/etc/nginx/conf.d/hop3.conf")
        nginx_enabled_path = None

    nginx_config_path.parent.mkdir(parents=True, exist_ok=True)
    nginx_config_path.write_text(nginx_config)
    print_success(f"Nginx config written to {nginx_config_path}")

    # Create symlink if using sites-available/sites-enabled
    if nginx_enabled_path:
        nginx_enabled_path.parent.mkdir(parents=True, exist_ok=True)
        if nginx_enabled_path.exists() or nginx_enabled_path.is_symlink():
            nginx_enabled_path.unlink()
        nginx_enabled_path.symlink_to(nginx_config_path)
        print_success("Nginx site enabled")

        # Remove default site if exists
        default_site = Path("/etc/nginx/sites-enabled/default")
        if default_site.exists() or default_site.is_symlink():
            default_site.unlink()
            print_info("Removed default nginx site")

    # Add include for app-specific configs
    _add_hop3_nginx_include()

    # Test nginx config
    try:
        run_cmd(["nginx", "-t"])
        print_success("Nginx configuration is valid")
    except CommandError as e:
        print_error(f"Nginx configuration test failed: {e.stderr[:200]}")
        return

    # Configure sudoers
    setup_sudoers()

    # Enable and start nginx
    run_cmd(["systemctl", "enable", "nginx"], check=False)
    run_cmd(["systemctl", "restart", "nginx"], check=False)
    print_success("Nginx enabled and started")


def _add_hop3_nginx_include() -> None:
    """Add include directive for hop3 app configs to nginx.conf."""
    nginx_conf = Path("/etc/nginx/nginx.conf")
    include_line = "include /home/hop3/nginx/*.conf;"

    if not nginx_conf.exists():
        print_warning("nginx.conf not found, skipping app include setup")
        return

    content = nginx_conf.read_text()

    if include_line in content:
        print_info("Hop3 app nginx include already configured")
        return

    # Create the nginx directory for app configs
    hop3_nginx_dir = HOME_DIR / "nginx"
    hop3_nginx_dir.mkdir(parents=True, exist_ok=True)
    hop3_uid = pwd.getpwnam(HOP3_USER).pw_uid
    hop3_gid = grp.getgrnam(HOP3_GROUP).gr_gid
    os.chown(hop3_nginx_dir, hop3_uid, hop3_gid)

    # Find the right place to add the include
    lines = content.split("\n")
    new_lines = []
    include_added = False

    for line in lines:
        new_lines.append(line)
        if not include_added and "include" in line:
            if "sites-enabled" in line or "conf.d" in line:
                indent = len(line) - len(line.lstrip())
                new_lines.append(" " * indent + include_line)
                include_added = True

    if include_added:
        nginx_conf.write_text("\n".join(new_lines))
        print_success("Added hop3 app nginx include to nginx.conf")
    else:
        print_warning("Could not find suitable location for nginx include")


def setup_sudoers() -> None:
    """Configure sudo permissions for hop3 user."""
    sudoers_file = Path("/etc/sudoers.d/hop3")

    try:
        sudoers_file.write_text(SUDOERS_CONTENT)
        os.chmod(sudoers_file, 0o440)

        # Validate with visudo
        result = subprocess.run(
            ["visudo", "-c", "-f", str(sudoers_file)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print_warning(f"Invalid sudoers file: {result.stderr}")
            sudoers_file.unlink()
            return

        print_success("Sudoers configured for hop3 service management")
    except Exception as e:
        print_warning(f"Could not configure sudoers: {e}")


# =============================================================================
# PostgreSQL
# =============================================================================


def setup_postgres(config: ServerInstallerConfig, distro: str) -> str | None:
    """Configure PostgreSQL.

    Returns:
        The generated postgres superuser password, or None if skipped.
    """
    if config.skip_postgres:
        print_info("Skipping PostgreSQL setup (--skip-postgres)")
        return None

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

    # Set a password for postgres superuser
    pg_password = "hop3_" + secrets.token_hex(16)

    # Use psql to set the password
    sql_cmd = f"ALTER USER postgres PASSWORD '{pg_password}';"
    result = run_cmd(
        ["su", "-", "postgres", "-c", f'psql -c "{sql_cmd}"'],
        check=False,
    )
    if result.returncode == 0:
        print_success("PostgreSQL superuser password configured")
    else:
        print_warning("Could not set PostgreSQL superuser password")
        return None

    return pg_password


# =============================================================================
# MySQL
# =============================================================================


def get_debian_mysql_credentials() -> tuple[str, str] | None:
    """Get MySQL credentials from Debian maintenance file.

    On Debian/Ubuntu, /etc/mysql/debian.cnf contains credentials for
    the debian-sys-maint user which has full privileges.

    Returns:
        Tuple of (user, password) or None if not available.
    """
    debian_cnf = Path("/etc/mysql/debian.cnf")
    if not debian_cnf.exists():
        return None

    try:
        content = debian_cnf.read_text()
        user = None
        password = None
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("user"):
                user = line.split("=")[1].strip()
            elif line.startswith("password"):
                password = line.split("=")[1].strip()
            if user and password:
                return (user, password)
    except Exception:
        pass
    return None


def reset_mysql_root_auth() -> bool:
    """Reset MySQL root authentication to socket auth.

    Uses Debian maintenance user or skip-grant-tables as fallback.

    Returns:
        True if reset was successful, False otherwise.
    """
    import time

    print_detail("Attempting to reset MySQL root authentication...")

    # Method 1: Try using Debian maintenance user
    creds = get_debian_mysql_credentials()
    if creds:
        user, password = creds
        print_detail(f"Using Debian maintenance user: {user}")
        result = run_cmd(
            [
                "mysql",
                f"-u{user}",
                f"-p{password}",
                "-e",
                "ALTER USER 'root'@'localhost' IDENTIFIED WITH auth_socket; FLUSH PRIVILEGES;",
            ],
            check=False,
        )
        if result.returncode == 0:
            print_detail("Reset via debian-sys-maint succeeded")
            return True

    # Method 2: Use skip-grant-tables (more invasive but reliable)
    print_detail("Trying skip-grant-tables method...")

    # Stop MySQL
    run_cmd(["systemctl", "stop", "mysql"], check=False)
    run_cmd(["systemctl", "stop", "mariadb"], check=False)
    time.sleep(2)

    # Start MySQL without authentication
    run_cmd(
        ["mysqld", "--skip-grant-tables", "--skip-networking", "--user=mysql"],
        check=False,
        timeout=5,  # This will timeout as mysqld runs in foreground, that's OK
    )
    time.sleep(3)

    # Reset root authentication
    result = run_cmd(
        [
            "mysql",
            "-e",
            "FLUSH PRIVILEGES; ALTER USER 'root'@'localhost' IDENTIFIED WITH auth_socket;",
        ],
        check=False,
    )

    # Kill the mysqld process
    run_cmd(["pkill", "-f", "skip-grant-tables"], check=False)
    time.sleep(2)

    # Restart MySQL normally
    run_cmd(["systemctl", "start", "mysql"], check=False)
    if run_cmd(["systemctl", "is-active", "mysql"], check=False).returncode != 0:
        run_cmd(["systemctl", "start", "mariadb"], check=False)
    time.sleep(2)

    return result.returncode == 0


def setup_mysql(config: ServerInstallerConfig, distro: str) -> str | None:
    """Configure MySQL.

    Returns:
        The generated MySQL password for hop3 user, or None if skipped/failed.
    """
    if not config.with_mysql:
        return None

    print_info("Configuring MySQL...")

    # Start MySQL service
    run_cmd(["systemctl", "enable", "mysql"], check=False)
    result = run_cmd(["systemctl", "start", "mysql"], check=False)

    if result.returncode != 0:
        # Try mariadb service name (some distros use this)
        run_cmd(["systemctl", "enable", "mariadb"], check=False)
        result = run_cmd(["systemctl", "start", "mariadb"], check=False)

    if result.returncode != 0:
        print_warning("Could not start MySQL service")
        return None

    print_success("MySQL service started")

    # Generate a secure password
    mysql_password = "hop3_" + secrets.token_hex(16)

    # First, test if we can connect to MySQL at all
    # Try different connection methods for MySQL root/admin access
    mysql_root_cmd = None

    # Build list of commands to try
    test_commands = [
        ["mysql"],  # Socket auth as current user (root)
        ["sudo", "mysql"],  # Socket auth via sudo
        ["mysql", "-u", "root"],  # Traditional root
    ]

    # Also try Debian maintenance user if available
    debian_creds = get_debian_mysql_credentials()
    if debian_creds:
        user, password = debian_creds
        test_commands.insert(0, ["mysql", f"-u{user}", f"-p{password}"])

    for test_cmd in test_commands:
        result = run_cmd(test_cmd + ["-e", "SELECT 1;"], check=False)
        if result.returncode == 0:
            mysql_root_cmd = test_cmd
            # Don't show password in logs
            display_cmd = " ".join(test_cmd)
            if debian_creds and debian_creds[1] in display_cmd:
                display_cmd = display_cmd.replace(debian_creds[1], "***")
            print_detail(f"MySQL admin access via: {display_cmd}")
            break

    if mysql_root_cmd is None:
        print_warning(
            "Cannot connect to MySQL as root - attempting to reset authentication"
        )

        # Try to reset MySQL root to use socket authentication
        # This is safe and allows the installer to proceed
        if reset_mysql_root_auth():
            # Retry connection after reset
            for test_cmd in [["mysql"], ["sudo", "mysql"]]:
                result = run_cmd(test_cmd + ["-e", "SELECT 1;"], check=False)
                if result.returncode == 0:
                    mysql_root_cmd = test_cmd
                    print_success("MySQL root access restored")
                    break

        if mysql_root_cmd is None:
            print_warning("Could not restore MySQL root access")
            print_detail("MySQL configuration may need manual intervention")
            return None

    # At this point mysql_root_cmd is guaranteed to be set
    assert mysql_root_cmd is not None
    root_cmd = mysql_root_cmd  # Capture in local variable for type checker

    def run_mysql_sql(sql: str) -> subprocess.CompletedProcess:
        """Run SQL using the working MySQL root connection."""
        return run_cmd(root_cmd + ["-e", sql], check=False)

    # Drop existing hop3 user if exists (clean slate)
    # Note: MySQL treats 'localhost' (socket) and '127.0.0.1' (TCP) as different hosts
    run_mysql_sql("DROP USER IF EXISTS 'hop3'@'localhost';")
    run_mysql_sql("DROP USER IF EXISTS 'hop3'@'127.0.0.1';")

    # Create hop3 user with password authentication for both localhost and 127.0.0.1
    # Use mysql_native_password for compatibility with mysql-connector-python
    result = run_mysql_sql(
        f"CREATE USER 'hop3'@'localhost' IDENTIFIED WITH mysql_native_password BY '{mysql_password}';"
    )
    if result.returncode != 0:
        print_warning("Failed to create MySQL user 'hop3'@'localhost'")
        if result.stderr:
            print_detail(result.stderr[:200])
        return None

    result = run_mysql_sql(
        f"CREATE USER 'hop3'@'127.0.0.1' IDENTIFIED WITH mysql_native_password BY '{mysql_password}';"
    )
    if result.returncode != 0:
        print_warning("Failed to create MySQL user 'hop3'@'127.0.0.1'")
        if result.stderr:
            print_detail(result.stderr[:200])
        return None

    # Grant all privileges to both hosts
    result = run_mysql_sql(
        "GRANT ALL PRIVILEGES ON *.* TO 'hop3'@'localhost' WITH GRANT OPTION;"
    )
    if result.returncode != 0:
        print_warning("Failed to grant privileges to hop3@localhost")
        if result.stderr:
            print_detail(result.stderr[:200])
        return None

    result = run_mysql_sql(
        "GRANT ALL PRIVILEGES ON *.* TO 'hop3'@'127.0.0.1' WITH GRANT OPTION;"
    )
    if result.returncode != 0:
        print_warning("Failed to grant privileges to hop3@127.0.0.1")
        if result.stderr:
            print_detail(result.stderr[:200])
        return None

    run_mysql_sql("FLUSH PRIVILEGES;")

    print_success("MySQL user 'hop3' created with privileges")

    # Verify the connection works with the new password (use 127.0.0.1 to match config)
    verify_result = run_cmd(
        [
            "mysql",
            "-u",
            "hop3",
            f"-p{mysql_password}",
            "-h",
            "127.0.0.1",
            "-e",
            "SELECT 1;",
        ],
        check=False,
    )

    if verify_result.returncode != 0:
        print_warning("MySQL user created but connection verification failed")
        if verify_result.stderr:
            print_detail(verify_result.stderr[:200])
        return None

    print_success("MySQL connection verified successfully")
    return mysql_password


# =============================================================================
# ACME / Let's Encrypt
# =============================================================================


def setup_acme(config: ServerInstallerConfig) -> None:
    """Install acme.sh for Let's Encrypt."""
    if config.skip_acme:
        print_info("Skipping ACME setup (--skip-acme)")
        return

    acme_sh = HOME_DIR / ".acme.sh" / "acme.sh"

    if acme_sh.exists():
        print_info("acme.sh already installed")
        return

    with Spinner("Installing acme.sh..."):
        run_as_hop3(
            "curl -fsSL https://raw.githubusercontent.com/Neilpang/acme.sh/master/acme.sh -o /tmp/acme.sh"
        )
        run_as_hop3("cd /tmp && bash acme.sh --install")
        run_cmd(["rm", "-f", "/tmp/acme.sh"])

    if acme_sh.exists():
        run_as_hop3(f"bash {acme_sh} --set-default-ca --server letsencrypt")
        print_success("acme.sh installed and configured")
    else:
        print_warning("acme.sh installation may have failed")


# =============================================================================
# Server Configuration
# =============================================================================


def write_server_config(
    pg_password: str | None,
    mysql_password: str | None,
    domain: str | None,
    secret_key: str | None = None,
) -> None:
    """Write hop3-server.toml configuration file."""
    config_file = HOME_DIR / "hop3-server.toml"

    lines = [
        "# Hop3 Server Configuration",
        "# Auto-generated by installer",
        "",
    ]

    # Add secret key for JWT token signing
    if secret_key:
        lines.extend(
            [
                "# Secret key for JWT token signing (required for authentication)",
                f'HOP3_SECRET_KEY = "{secret_key}"',
                "",
            ]
        )

    if domain:
        lines.extend(
            [
                "# Admin UI domain",
                f'ADMIN_DOMAIN = "{domain}"',
                "",
            ]
        )

    if pg_password:
        lines.extend(
            [
                "# PostgreSQL admin connection settings",
                'POSTGRES_HOST = "127.0.0.1"',
                f'POSTGRES_SUPERUSER_PASSWORD = "{pg_password}"',
                "",
            ]
        )

    if mysql_password:
        lines.extend(
            [
                "# MySQL admin connection settings",
                'MYSQL_HOST = "127.0.0.1"',
                'MYSQL_SUPERUSER = "hop3"',
                f'MYSQL_SUPERUSER_PASSWORD = "{mysql_password}"',
                "",
            ]
        )

    config_file.write_text("\n".join(lines))

    hop3_uid = pwd.getpwnam(HOP3_USER).pw_uid
    hop3_gid = grp.getgrnam(HOP3_GROUP).gr_gid
    os.chown(config_file, hop3_uid, hop3_gid)
    os.chmod(config_file, 0o600)

    print_success(f"Server configuration written to {config_file}")


# =============================================================================
# Verification
# =============================================================================


def verify_mysql_config() -> bool:
    """Verify MySQL configuration is correctly set up.

    Checks that hop3 user can connect to MySQL and that
    the config file has the proper settings.

    Returns:
        True if MySQL is properly configured, False otherwise.
    """
    config_file = HOME_DIR / "hop3-server.toml"

    # Check that config file has MySQL password
    if not config_file.exists():
        print_warning("Config file not found")
        return False

    config_content = config_file.read_text()
    if "MYSQL_SUPERUSER_PASSWORD" not in config_content:
        print_warning("MySQL password not in config file")
        return False

    # Test MySQL connection as hop3 user using the config
    # Extract password from config
    mysql_password = None
    for line in config_content.split("\n"):
        if "MYSQL_SUPERUSER_PASSWORD" in line and "=" in line:
            # Parse: MYSQL_SUPERUSER_PASSWORD = "value"
            value = line.split("=", 1)[1].strip().strip('"')
            mysql_password = value
            break

    if not mysql_password:
        print_warning("Could not extract MySQL password from config")
        return False

    # Test connection with the hop3 MySQL user
    result = run_cmd(
        ["mysql", "-u", "hop3", f"-p{mysql_password}", "-e", "SELECT 1;"],
        check=False,
        capture=True,
    )

    if result.returncode != 0:
        print_warning("MySQL connection test failed")
        if result.stderr:
            print_detail(result.stderr.strip()[:200])
        return False

    return True


def verify_installation(config: ServerInstallerConfig) -> bool:
    """Verify the installation."""
    hop_server = VENV_DIR / "bin" / "hop3-server"
    all_ok = True

    if not hop_server.exists():
        print_error("hop3-server not found")
        return False

    # Check services
    for service, name in [
        ("hop3-server", "hop3-server service"),
        ("nginx", "nginx service"),
        ("uwsgi-hop3", "uwsgi-hop3 service"),
    ]:
        result = run_cmd(["systemctl", "is-active", service], capture=True, check=False)
        if result.stdout.strip() == "active":
            print_success(f"{name} is running")
        else:
            print_warning(f"{name} is not running")
            print_detail(f"Check with: sudo systemctl status {service}")

    # Check SSL
    if SSL_CERT.exists() and SSL_KEY.exists():
        print_success("SSL certificate is configured")
    else:
        print_warning("SSL certificate not found")

    # Check PostgreSQL if configured
    config_file = HOME_DIR / "hop3-server.toml"
    if config_file.exists():
        config_content = config_file.read_text()

        if "POSTGRES_SUPERUSER_PASSWORD" in config_content:
            result = run_cmd(
                ["systemctl", "is-active", "postgresql"],
                capture=True,
                check=False,
            )
            if result.stdout.strip() == "active":
                print_success("PostgreSQL service is running")
            else:
                print_warning("PostgreSQL service is not running")
                all_ok = False

        # Check MySQL - full end-to-end test
        if "MYSQL_SUPERUSER_PASSWORD" in config_content:
            result = run_cmd(
                ["systemctl", "is-active", "mysql"],
                capture=True,
                check=False,
            )
            if result.returncode != 0:
                result = run_cmd(
                    ["systemctl", "is-active", "mariadb"],
                    capture=True,
                    check=False,
                )
            if result.stdout.strip() == "active":
                # Service is running, now test configuration
                if verify_mysql_config():
                    print_success("MySQL configuration verified")
                else:
                    print_error("MySQL configuration test FAILED")
                    all_ok = False
            else:
                print_warning("MySQL service is not running")
                all_ok = False

    return all_ok


def print_final_message(config: ServerInstallerConfig) -> None:
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
    print("    sudo systemctl status nginx")
    print()
    print(f"  {Colors.BOLD}Logs:{Colors.RESET}")
    print("    sudo journalctl -u hop3-server -f")
    print()
    print(f"  {Colors.BOLD}Next steps:{Colors.RESET}")
    print("    1. Add your SSH key:  ssh-copy-id hop3@your-server")
    print("    2. Deploy an app:     hop3 deploy your-app.git")
    print()


# =============================================================================
# CLI Argument Parsing
# =============================================================================


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    env_config = ServerInstallerConfig.from_env()

    parser = argparse.ArgumentParser(
        prog="install-server.py",
        description="Install the Hop3 Server. Must be run as root.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  sudo python3 install-server.py                  Install with PostgreSQL only
  sudo python3 install-server.py --with docker    Install with PostgreSQL + Docker
  sudo python3 install-server.py --with all       Install all optional features
  sudo python3 install-server.py --domain hop3.example.com
                                                  Install with Let's Encrypt cert

Optional Features (--with):
  docker      Docker container runtime
  mysql       MySQL database
  redis       Redis cache/store
  all         Install all optional features
""",
    )

    parser.add_argument(
        "--version",
        metavar="VERSION",
        default=env_config.version,
        help="Install a specific version (e.g., 0.4.0)",
    )
    parser.add_argument(
        "--git",
        action="store_true",
        default=env_config.use_git,
        help="Install from git repository",
    )
    parser.add_argument(
        "--branch",
        metavar="BRANCH",
        default=env_config.branch,
        help=f"Git branch to install from (default: {DEFAULT_BRANCH})",
    )
    parser.add_argument(
        "--local-path",
        metavar="PATH",
        default=env_config.local_path,
        help="Install from a local directory",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=env_config.force,
        help="Force reinstall",
    )
    parser.add_argument(
        "--skip-deps",
        action="store_true",
        default=env_config.skip_deps,
        help="Skip system dependency installation",
    )
    parser.add_argument(
        "--skip-nginx",
        action="store_true",
        default=env_config.skip_nginx,
        help="Skip nginx setup",
    )
    parser.add_argument(
        "--skip-postgres",
        action="store_true",
        default=env_config.skip_postgres,
        help="Skip PostgreSQL setup",
    )
    parser.add_argument(
        "--with",
        dest="with_features",
        metavar="FEATURES",
        default=",".join(env_config.features) if env_config.features else "",
        help="Comma-separated list of features (mysql,redis,docker,all)",
    )
    parser.add_argument(
        "--skip-acme",
        action="store_true",
        default=env_config.skip_acme,
        help="Skip ACME/Let's Encrypt setup",
    )
    parser.add_argument(
        "--domain",
        metavar="DOMAIN",
        default=env_config.domain,
        help="Domain name for Let's Encrypt certificate",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=env_config.verbose,
        help="Show verbose output",
    )

    return parser


# =============================================================================
# Main
# =============================================================================


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    check_python_version()

    parser = create_parser()
    args = parser.parse_args()

    # Convert args to config
    features = parse_features(args.with_features)
    config = ServerInstallerConfig(
        version=args.version,
        use_git=args.git,
        branch=args.branch,
        local_path=args.local_path,
        force=args.force,
        skip_deps=args.skip_deps,
        skip_nginx=args.skip_nginx,
        skip_postgres=args.skip_postgres,
        skip_acme=args.skip_acme,
        domain=args.domain,
        verbose=args.verbose,
        features=features,
    )

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

    if config.features:
        print_info(f"Optional features: {', '.join(sorted(config.features))}")

    total_steps = 11

    # Step 1: System dependencies
    print_step(1, total_steps, "Installing system dependencies...")
    try:
        install_system_deps(distro, config)
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
        install_package(config)
    except CommandError as e:
        print_error("Failed to install hop3-server")
        # Always show error output
        if e.stdout:
            print_detail("--- stdout ---")
            for line in e.stdout.strip().split("\n")[-20:]:
                print_detail(line)
        if e.stderr:
            print_detail("--- stderr ---")
            for line in e.stderr.strip().split("\n")[-20:]:
                print_detail(line)
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
    secret_key = None
    try:
        secret_key = setup_systemd()
    except CommandError as e:
        print_warning(f"Systemd setup issue: {e.stderr[:100]}")

    # Step 8: SSL certificates
    print_step(8, total_steps, "Setting up SSL certificates...")
    try:
        setup_ssl_selfsigned()
    except CommandError as e:
        print_warning(f"SSL setup issue: {e.stderr[:100]}")

    # Step 9: Nginx
    print_step(9, total_steps, "Configuring nginx...")
    try:
        setup_nginx(config)
    except CommandError as e:
        print_warning(f"Nginx setup issue: {e.stderr[:100]}")

    # Step 10: PostgreSQL
    print_step(10, total_steps, "Configuring PostgreSQL...")
    pg_password = None
    try:
        pg_password = setup_postgres(config, distro)
    except CommandError as e:
        print_warning(f"PostgreSQL setup issue: {e.stderr[:100]}")

    # Step 11: MySQL (if requested)
    print_step(11, total_steps, "Configuring MySQL...")
    mysql_password = None
    try:
        mysql_password = setup_mysql(config, distro)
    except CommandError as e:
        print_warning(f"MySQL setup issue: {e.stderr[:100]}")

    # Write server config (including secret key for CLI commands)
    try:
        write_server_config(pg_password, mysql_password, config.domain, secret_key)
    except Exception as e:
        print_warning(f"Config write issue: {e}")

    # ACME setup
    try:
        setup_acme(config)
    except CommandError as e:
        print_warning(f"ACME setup issue: {e.stderr[:100]}")

    # Verify
    print()
    if not verify_installation(config):
        print_error("Installation verification failed!")
        print_info("Please check the errors above and fix the configuration.")
        return 1

    # Success
    print_final_message(config)

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
