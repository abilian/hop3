# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Server setup and management for demos."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

from lib.commands import CommandError, run_local, run_ssh
from lib.output import pause, print_error, print_info, print_step, print_success

if TYPE_CHECKING:
    from lib.context import DemoContext


def verify_ssh_access(ctx: DemoContext) -> None:
    """Verify SSH access to the server."""
    print_step("Verifying SSH access to the server...")
    result = run_ssh(ctx, "echo 'SSH connection successful'", show=False, check=False)
    if result.returncode != 0:
        print_error(f"Cannot connect to {ctx.ssh_target}")
        print_info("Please ensure SSH key authentication is configured.")
        msg = f"Cannot connect to {ctx.ssh_target}"
        raise CommandError(msg)
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
        msg = f"Unsupported Ubuntu version: {result.stdout.strip()}"
        raise CommandError(msg)
    print_success(f"Ubuntu {version_found} LTS detected")


def check_hop3_installed(ctx: DemoContext) -> bool:
    """Check if Hop3 is installed on the server."""
    print_step("Checking if Hop3 is installed...")
    result = run_ssh(
        ctx, "test -f /home/hop3/venv/bin/hop-server", show=False, check=False
    )
    if result.returncode == 0:
        print_success("Hop3 is installed")
        return True
    print_info("Hop3 is not installed")
    return False


def install_hop3(ctx: DemoContext) -> None:
    """Install Hop3 on the server."""
    if not ctx.installer_path.exists():
        print_error("Cannot find Hop3 installer.")
        msg = f"Installer not found: {ctx.installer_path}"
        raise CommandError(msg)

    # Copy installer to server
    print_step("Copying installer to server...")
    run_local(
        f"scp -o StrictHostKeyChecking=accept-new {ctx.installer_path} {ctx.ssh_target}:/tmp/install-server.py"
    )
    print_success("Installer copied to server")
    pause(ctx.pause_between_steps)

    # Run installer
    print_step("Running Hop3 installer (this may take a few minutes)...")
    if ctx.use_local_code:
        # First sync local code, then install from local path
        sync_local_code(ctx)
        run_ssh(
            ctx,
            "python3 /tmp/install-server.py --local-path /tmp/hop3-server --verbose",
        )
    else:
        print_info("Installing from git branch: devel")
        run_ssh(ctx, "python3 /tmp/install-server.py --git --branch devel --verbose")
    print_success("Hop3 installation completed")
    pause(ctx.pause_between_steps)

    # Verify services
    print_step("Verifying services...")
    run_ssh(ctx, "systemctl status hop3-server --no-pager", check=False)
    run_ssh(ctx, "systemctl status nginx --no-pager", check=False)
    print_success("Hop3 services are running")


def sync_local_code(ctx: DemoContext) -> None:
    """Sync local hop3-server code to the server using rsync."""
    print_step("Syncing local hop3-server code to server...")

    server_pkg = ctx.packages_path / "hop3-server"
    if not server_pkg.exists():
        print_error(f"Cannot find hop3-server package at {server_pkg}")
        msg = f"Package not found: {server_pkg}"
        raise CommandError(msg)

    # Rsync the package to server
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
        msg = "Failed to sync code to server"
        raise CommandError(msg)
    print_success("Local code synced to server")


def update_hop3_server(ctx: DemoContext) -> None:
    """Update hop3-server on the remote server."""
    print_step("Updating hop3-server to latest version...")

    if ctx.use_local_code:
        # Sync local code and install from path
        sync_local_code(ctx)
        print_info("Installing from local path...")
        run_ssh(
            ctx,
            "/home/hop3/venv/bin/pip install --upgrade /tmp/hop3-server",
            show=False,
        )
    else:
        # Build wheel locally and install
        print_info("Building hop3-server package locally...")
        result = run_local(
            f"cd {ctx.hop3_repo} && uv build packages/hop3-server",
            show=False,
            check=False,
        )
        if result.returncode != 0:
            print_error("Failed to build hop3-server package.")
            msg = "Failed to build hop3-server package"
            raise CommandError(msg)

        # Find the built wheel (uv build outputs to repo root's dist/)
        dist_dir = ctx.dist_path
        wheels = list(dist_dir.glob("hop3_server-*.whl"))
        if not wheels:
            print_error("No wheel file found after build.")
            msg = "No wheel file found after build"
            raise CommandError(msg)
        wheel_path = max(wheels, key=lambda p: p.stat().st_mtime)

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

    # Restart hop3-server to pick up changes
    print_info("Restarting hop3-server...")
    run_ssh(ctx, "systemctl restart hop3-server", show=False)

    # Wait for server to start
    import time

    time.sleep(2)

    print_success("hop3-server updated")


def configure_server_settings(ctx: DemoContext) -> None:
    """Configure server settings for demos.

    This updates hop3-server.toml with demo-specific settings:
    - HOP3_LOG_LEVEL = "DEBUG" for detailed logging

    Note: PostgreSQL password and host settings are configured by the installer,
    not the demo launcher. If PostgreSQL addons fail, re-run the installer.
    """
    print_step("Configuring server settings for demos...")

    # Update config to add DEBUG logging (preserves existing settings from installer)
    config_script = """\
import toml
from pathlib import Path

config_file = Path("/home/hop3/hop3-server.toml")

# Load existing config (installer should have created it with PostgreSQL settings)
if config_file.exists():
    config_data = toml.load(config_file)
else:
    config_data = {}

# Set DEBUG logging for demos
config_data["HOP3_LOG_LEVEL"] = "DEBUG"

# Write config back
with config_file.open("w") as f:
    f.write("# Hop3 Server Configuration\\n")
    f.write("# PostgreSQL settings from installer, DEBUG logging from demo launcher\\n\\n")
    toml.dump(config_data, f)

print(f"Config file: {config_file}")
print(f"  HOP3_LOG_LEVEL: {config_data.get('HOP3_LOG_LEVEL', 'NOT SET')}")
print(f"  POSTGRES_HOST: {config_data.get('POSTGRES_HOST', 'NOT SET')}")
print(f"  POSTGRES_SUPERUSER_PASSWORD: {'SET' if config_data.get('POSTGRES_SUPERUSER_PASSWORD') else 'NOT SET'}")
print("Server config updated")
"""
    # Write script to temp file and execute using hop3's virtualenv Python (has toml)
    encoded = base64.b64encode(config_script.encode()).decode()
    run_ssh(
        ctx,
        f"echo {encoded} | base64 -d > /tmp/configure_hop3.py && sudo /home/hop3/venv/bin/python /tmp/configure_hop3.py && rm /tmp/configure_hop3.py",
        show=False,
    )
    print_success("Server settings configured (DEBUG logging enabled)")

    # Restart server to pick up changes
    print_info("Restarting hop3-server to apply configuration...")
    run_ssh(ctx, "systemctl restart hop3-server", show=False)
    import time

    time.sleep(2)
    print_success("Server restarted with new configuration")


def ensure_docker(ctx: DemoContext) -> None:
    """Ensure Docker is installed and hop3 user has access."""
    print_step("Checking if Docker is installed...")
    result = run_ssh(ctx, "which docker", show=False, check=False)
    if result.returncode != 0:
        print_info("Docker is not installed. Installing docker.io package...")
        run_ssh(ctx, "apt-get update -qq && apt-get install -y -qq docker.io")
        run_ssh(ctx, "systemctl enable docker && systemctl start docker")
        print_success("Docker installed and started")
    else:
        print_success("Docker is installed")
    pause(ctx.pause_between_steps)

    # Ensure hop3 user is in docker group
    print_step("Ensuring hop3 user has Docker access...")
    result = run_ssh(ctx, "groups hop3 | grep -q docker", show=False, check=False)
    if result.returncode != 0:
        print_info("Adding hop3 user to docker group...")
        run_ssh(ctx, "usermod -aG docker hop3")
        # Restart hop3-server to pick up new group
        print_info("Restarting hop3-server to apply group changes...")
        run_ssh(ctx, "systemctl restart hop3-server")
        import time

        time.sleep(2)
        print_success("hop3 user added to docker group")
    else:
        print_success("hop3 user has Docker access")

    # Ensure PostgreSQL is configured for Docker container access
    ensure_postgres_docker_access(ctx)


def ensure_postgres_docker_access(ctx: DemoContext) -> None:
    """Configure PostgreSQL to accept connections from Docker containers.

    Docker containers connect via host.docker.internal which routes to 172.17.x.x.
    PostgreSQL must be configured to:
    1. Listen on all interfaces (not just localhost)
    2. Allow password auth from Docker bridge network (172.17.0.0/16)
    """
    print_step("Configuring PostgreSQL for Docker container access...")

    # Check if already configured (look for Docker network rules)
    result = run_ssh(
        ctx,
        "grep -q '172.16.0.0/12' /etc/postgresql/*/main/pg_hba.conf 2>/dev/null",
        show=False,
        check=False,
    )
    if result.returncode == 0:
        print_success("PostgreSQL already configured for Docker access")
        return

    # Find PostgreSQL config directory and configure
    config_script = """\
import subprocess
from pathlib import Path

# Find PostgreSQL config directory
pg_dirs = list(Path("/etc/postgresql").glob("*/main"))
if not pg_dirs:
    print("ERROR: PostgreSQL config directory not found")
    exit(1)

pg_conf_dir = pg_dirs[0]
pg_conf = pg_conf_dir / "postgresql.conf"
pg_hba = pg_conf_dir / "pg_hba.conf"

# Update listen_addresses
conf_content = pg_conf.read_text()
if "listen_addresses = '*'" not in conf_content:
    new_lines = []
    for line in conf_content.split("\\n"):
        if line.strip().startswith("listen_addresses"):
            new_lines.append(f"# {line}  # commented by hop3")
        else:
            new_lines.append(line)
    new_lines.append("")
    new_lines.append("# Added by hop3 for Docker container access")
    new_lines.append("listen_addresses = '*'")
    pg_conf.write_text("\\n".join(new_lines))
    print("Updated postgresql.conf: listen_addresses = '*'")

# Add pg_hba.conf rule for Docker networks
# 172.16.0.0/12 covers all Docker networks (172.16.x.x - 172.31.x.x)
# including default bridge (172.17.x.x) and docker-compose networks (172.18+)
hba_content = pg_hba.read_text()
if "172.16.0.0/12" not in hba_content:
    new_lines = []
    docker_rule_added = False
    for line in hba_content.split("\\n"):
        if not docker_rule_added and line.strip().startswith("host"):
            new_lines.append("# Added by hop3 for Docker container access")
            new_lines.append("host    all    all    172.16.0.0/12    scram-sha-256")
            new_lines.append("")
            docker_rule_added = True
        new_lines.append(line)
    if not docker_rule_added:
        new_lines.append("")
        new_lines.append("# Added by hop3 for Docker container access")
        new_lines.append("host    all    all    172.16.0.0/12    scram-sha-256")
    pg_hba.write_text("\\n".join(new_lines))
    print("Updated pg_hba.conf: added Docker network rule")

print("PostgreSQL configured for Docker access")
"""
    encoded = base64.b64encode(config_script.encode()).decode()
    result = run_ssh(
        ctx,
        f"echo {encoded} | base64 -d > /tmp/pg_docker.py && sudo python3 /tmp/pg_docker.py && rm /tmp/pg_docker.py",
        show=False,
        check=False,
    )

    if result.returncode != 0:
        print_error(f"Failed to configure PostgreSQL: {result.stderr}")
        return

    # Restart PostgreSQL to apply changes
    print_info("Restarting PostgreSQL to apply changes...")
    run_ssh(ctx, "systemctl restart postgresql", show=False, check=False)
    import time

    time.sleep(2)
    print_success("PostgreSQL configured for Docker container access")


def ensure_redis(ctx: DemoContext) -> None:
    """Ensure Redis is installed and configured for Docker container access.

    This:
    1. Installs redis-server if not present
    2. Configures Redis to bind to all interfaces (for Docker access)
    3. Enables and starts the redis-server service
    """
    print_step("Checking if Redis is installed...")
    result = run_ssh(ctx, "which redis-server", show=False, check=False)
    if result.returncode != 0:
        print_info("Redis is not installed. Installing redis-server...")
        run_ssh(ctx, "apt-get update -qq && apt-get install -y -qq redis-server")
        print_success("Redis installed")
    else:
        print_success("Redis is installed")
    pause(ctx.pause_between_steps)

    # Configure Redis to bind to all interfaces for Docker access
    print_step("Configuring Redis for Docker container access...")
    result = run_ssh(
        ctx,
        "grep -q '^bind 0.0.0.0' /etc/redis/redis.conf 2>/dev/null",
        show=False,
        check=False,
    )
    if result.returncode != 0:
        # Update bind address to allow connections from Docker containers
        print_info("Updating Redis bind address...")
        config_script = """\
import re
from pathlib import Path

redis_conf = Path("/etc/redis/redis.conf")
content = redis_conf.read_text()

# Replace bind directive to allow all interfaces
# Default is usually "bind 127.0.0.1 ::1" or "bind 127.0.0.1"
new_content = re.sub(
    r'^bind\\s+.*$',
    'bind 0.0.0.0',
    content,
    flags=re.MULTILINE
)

# Also disable protected mode since we're binding to all interfaces
new_content = re.sub(
    r'^protected-mode\\s+yes',
    'protected-mode no',
    new_content,
    flags=re.MULTILINE
)

redis_conf.write_text(new_content)
print("Redis configured to bind to 0.0.0.0")
"""
        encoded = base64.b64encode(config_script.encode()).decode()
        run_ssh(
            ctx,
            f"echo {encoded} | base64 -d > /tmp/redis_config.py && sudo python3 /tmp/redis_config.py && rm /tmp/redis_config.py",
            show=False,
        )

        # Restart Redis to apply changes
        print_info("Restarting Redis...")
        run_ssh(ctx, "systemctl restart redis-server", show=False)
        import time

        time.sleep(2)
        print_success("Redis configured for Docker access")
    else:
        print_success("Redis already configured for Docker access")

    # Ensure Redis is enabled and running
    print_step("Ensuring Redis service is running...")
    run_ssh(ctx, "systemctl enable redis-server", show=False, check=False)
    run_ssh(ctx, "systemctl start redis-server", show=False, check=False)
    result = run_ssh(ctx, "systemctl is-active redis-server", show=False, check=False)
    if "active" in result.stdout:
        print_success("Redis service is running")
    else:
        print_error("Redis service is not running")
        run_ssh(ctx, "systemctl status redis-server --no-pager", check=False)
