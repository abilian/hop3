# Copyright (c) 2025, Abilian SAS
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
import shutil
import subprocess
import sys
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


# =============================================================================
# Systemd Services
# =============================================================================


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
    run_cmd(["systemctl", "start", "uwsgi-hop3"], check=False)

    print_success("Systemd services configured")


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


def write_server_config(pg_password: str | None, domain: str | None) -> None:
    """Write hop3-server.toml configuration file."""
    config_file = HOME_DIR / "hop3-server.toml"

    lines = [
        "# Hop3 Server Configuration",
        "# Auto-generated by installer",
        "",
    ]

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

    config_file.write_text("\n".join(lines))

    hop3_uid = pwd.getpwnam(HOP3_USER).pw_uid
    hop3_gid = grp.getgrnam(HOP3_GROUP).gr_gid
    os.chown(config_file, hop3_uid, hop3_gid)
    os.chmod(config_file, 0o600)

    print_success(f"Server configuration written to {config_file}")


# =============================================================================
# Verification
# =============================================================================


def verify_installation() -> bool:
    """Verify the installation."""
    hop_server = VENV_DIR / "bin" / "hop-server"

    if not hop_server.exists():
        print_error("hop-server not found")
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

    return True


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

    total_steps = 10

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
    try:
        setup_systemd()
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

    # Write server config
    try:
        write_server_config(pg_password, config.domain)
    except Exception as e:
        print_warning(f"Config write issue: {e}")

    # ACME setup
    try:
        setup_acme(config)
    except CommandError as e:
        print_warning(f"ACME setup issue: {e.stderr[:100]}")

    # Verify
    print()
    verify_installation()

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
