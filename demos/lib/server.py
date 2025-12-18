# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Server setup and management for demos."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from lib.commands import CommandError, run_local, run_ssh
from lib.output import pause, print_error, print_info, print_step, print_success

if TYPE_CHECKING:
    from lib.context import DemoContext

# Directory containing helper scripts to copy to server
SCRIPTS_DIR = Path(__file__).parent / "scripts"


def _run_remote_script(
    ctx: DemoContext,
    script_name: str,
    python_bin: str = "python3",
    sudo: bool = False,
    show: bool = False,
) -> None:
    """Copy a script to the server and execute it.

    Args:
        ctx: Demo context
        script_name: Name of script in lib/scripts/ directory
        python_bin: Python interpreter to use (default: python3)
        sudo: Run with sudo (default: False)
        show: Show command output (default: False)
    """
    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        raise CommandError(f"Script not found: {script_path}")

    remote_path = f"/tmp/{script_name}"

    # Copy script to server
    run_local(
        f"scp -o StrictHostKeyChecking=accept-new {script_path} {ctx.ssh_target}:{remote_path}",
        show=False,
    )

    # Execute and cleanup
    sudo_prefix = "sudo " if sudo else ""
    run_ssh(
        ctx,
        f"{sudo_prefix}{python_bin} {remote_path} && rm {remote_path}",
        show=show,
    )


def clean_server(ctx: DemoContext) -> None:
    """Clean the server completely before running demos.

    This removes:
    - All deployed apps (Docker containers and data)
    - The hop3 home directory (/home/hop3)
    - The hop3 database
    - Nginx configurations for apps
    """
    print_step("Cleaning server before demo run...")

    # Stop hop3-server service if running
    print_info("Stopping hop3-server service...")
    run_ssh(ctx, "systemctl stop hop3-server 2>/dev/null || true", show=False, check=False)

    # Stop and remove any Docker containers that might be running for apps
    print_info("Stopping any running Docker containers...")
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

    # Remove app nginx configurations
    print_info("Removing nginx app configurations...")
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

    # Reload nginx to apply config removal
    run_ssh(ctx, "systemctl reload nginx 2>/dev/null || true", show=False, check=False)

    # Remove the hop3 home directory completely (includes database, apps, venv)
    print_info("Removing /home/hop3 directory...")
    run_ssh(ctx, "rm -rf /home/hop3", show=False, check=False)

    # Recreate hop3 user home directory
    print_info("Recreating hop3 user home directory...")
    run_ssh(ctx, "mkdir -p /home/hop3 && chown hop3:hop3 /home/hop3", show=False, check=False)

    print_success("Server cleaned successfully")


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

    # Build installer command with optional admin domain
    domain_arg = f" --domain {ctx.admin_domain}" if ctx.admin_domain else ""
    # Install all optional features (MySQL, Redis) for demos
    with_all = " --with all"

    if ctx.use_local_code:
        # First sync local code, then install from local path
        sync_local_code(ctx)
        run_ssh(
            ctx,
            f"python3 /tmp/install-server.py --local-path /tmp/hop3-server{domain_arg}{with_all} --verbose",
        )
    else:
        print_info("Installing from git branch: devel")
        run_ssh(
            ctx,
            f"python3 /tmp/install-server.py --git --branch devel{domain_arg}{with_all} --verbose",
        )
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
        if result.stdout:
            print(f"  stdout: {result.stdout.strip()}")
        if result.stderr:
            print(f"  stderr: {result.stderr.strip()}")
        msg = f"Failed to sync code to server (exit code {result.returncode})"
        raise CommandError(msg)

    # Fix permissions so hop3 user can read the code during pip install
    run_ssh(
        ctx,
        "chmod -R a+rX /tmp/hop3-server",
        show=False,
        check=False,
    )
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
    - HOP3_SECRET_KEY = generated secret for token signing

    Note: PostgreSQL password and host settings are configured by the installer,
    not the demo launcher. If PostgreSQL addons fail, re-run the installer.
    """
    print_step("Configuring server settings for demos...")

    # Run configuration script (uses hop3's venv Python which has toml installed)
    _run_remote_script(
        ctx,
        "configure_hop3.py",
        python_bin="/home/hop3/venv/bin/python",
        sudo=True,
    )
    print_success("Server settings configured (DEBUG logging enabled)")

    # Restart server to pick up changes
    print_info("Restarting hop3-server to apply configuration...")
    run_ssh(ctx, "systemctl restart hop3-server", show=False)
    import time

    time.sleep(2)
    print_success("Server restarted with new configuration")


def ensure_docker(ctx: DemoContext) -> None:
    """Verify Docker is installed and hop3 user has access.

    Note: Docker should be installed by the installer (--with docker or --with all).
    This function only verifies the installation and configures hop3 user access.
    """
    print_step("Checking if Docker is installed...")
    result = run_ssh(ctx, "which docker", show=False, check=False)
    if result.returncode != 0:
        print_error("Docker is not installed!")
        print_info("Docker should be installed by the installer with --with docker")
        print_info("Re-run the installer with: --with all")
        msg = "Docker not installed - run installer with --with docker"
        raise RuntimeError(msg)
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

    Docker containers connect via host.docker.internal which routes to various IPs.
    PostgreSQL must be configured to:
    1. Listen on all interfaces (not just localhost)
    2. Allow password auth from Docker networks (172.16.0.0/12 and 192.168.0.0/16)
    """
    print_step("Configuring PostgreSQL for Docker container access...")

    # Check if already configured (look for Docker network rules - both ranges)
    result = run_ssh(
        ctx,
        "grep -q '192.168.0.0/16' /etc/postgresql/*/main/pg_hba.conf 2>/dev/null",
        show=False,
        check=False,
    )
    if result.returncode == 0:
        print_success("PostgreSQL already configured for Docker access")
        return

    # Run configuration script
    _run_remote_script(ctx, "configure_pg_docker.py", sudo=True)

    # Restart PostgreSQL to apply changes
    print_info("Restarting PostgreSQL to apply changes...")
    run_ssh(ctx, "systemctl restart postgresql", show=False, check=False)
    import time

    time.sleep(2)
    print_success("PostgreSQL configured for Docker container access")


def ensure_postgres(ctx: DemoContext) -> None:
    """Verify PostgreSQL is installed and properly configured for Hop3.

    Note: PostgreSQL should be installed by the installer.
    This function verifies the installation and checks connectivity.
    """
    print_step("Checking if PostgreSQL is installed...")
    result = run_ssh(ctx, "which psql", show=False, check=False)
    if result.returncode != 0:
        print_error("PostgreSQL is not installed!")
        print_info("PostgreSQL should be installed by the installer")
        msg = "PostgreSQL not installed"
        raise RuntimeError(msg)
    print_success("PostgreSQL is installed")

    # Verify PostgreSQL service is running
    print_step("Checking PostgreSQL service status...")
    result = run_ssh(ctx, "systemctl is-active postgresql", show=False, check=False)
    if "active" not in result.stdout:
        print_error("PostgreSQL service is not running")
        run_ssh(ctx, "systemctl status postgresql --no-pager", check=False)
        msg = "PostgreSQL service not running"
        raise RuntimeError(msg)
    print_success("PostgreSQL service is running")

    # Verify hop3-server has PostgreSQL password configured
    print_step("Verifying PostgreSQL password authentication...")
    result = run_ssh(
        ctx,
        "grep -q POSTGRES_SUPERUSER_PASSWORD /home/hop3/hop3-server.toml",
        show=False,
        check=False,
    )
    if result.returncode != 0:
        print_error("PostgreSQL password not configured in hop3-server.toml")
        print_info("The installer should have configured PostgreSQL credentials")
        msg = "PostgreSQL password not configured"
        raise RuntimeError(msg)
    print_success("PostgreSQL password authentication configured")


def ensure_mysql(ctx: DemoContext) -> None:
    """Verify MySQL is installed and properly configured for Hop3.

    Note: MySQL should be installed by the installer (--with mysql or --with all).
    This function verifies the installation and checks that password auth is working.
    """
    print_step("Checking if MySQL is installed...")
    result = run_ssh(ctx, "which mysql", show=False, check=False)
    if result.returncode != 0:
        print_error("MySQL is not installed!")
        print_info("MySQL should be installed by the installer with --with mysql")
        print_info("Re-run the installer with: --with all")
        msg = "MySQL not installed - run installer with --with mysql"
        raise RuntimeError(msg)
    print_success("MySQL is installed")

    # Verify MySQL service is running
    print_step("Checking MySQL service status...")
    result = run_ssh(ctx, "systemctl is-active mysql", show=False, check=False)
    if "active" not in result.stdout:
        print_error("MySQL service is not running")
        run_ssh(ctx, "systemctl status mysql --no-pager", check=False)
        msg = "MySQL service not running"
        raise RuntimeError(msg)
    print_success("MySQL service is running")

    # Verify hop3-server can connect to MySQL (password auth configured)
    print_step("Verifying MySQL password authentication...")
    result = run_ssh(
        ctx,
        "grep -q MYSQL_SUPERUSER_PASSWORD /home/hop3/hop3-server.toml",
        show=False,
        check=False,
    )
    if result.returncode != 0:
        print_error("MySQL password not configured in hop3-server.toml")
        print_info("The installer should have configured MySQL credentials")
        print_info("Re-run the installer with: --with all")
        msg = "MySQL password not configured"
        raise RuntimeError(msg)
    print_success("MySQL password authentication configured")


def ensure_redis(ctx: DemoContext) -> None:
    """Verify Redis is installed and running.

    Note: Redis should be installed by the installer (--with redis or --with all).
    This function verifies the installation is correct.
    """
    print_step("Checking if Redis is installed...")
    result = run_ssh(ctx, "which redis-server", show=False, check=False)
    if result.returncode != 0:
        print_error("Redis is not installed!")
        print_info("Redis should be installed by the installer with --with redis")
        print_info("Re-run the installer with: --with all")
        msg = "Redis not installed - run installer with --with redis"
        raise RuntimeError(msg)
    print_success("Redis is installed")

    # Verify Redis service is running
    print_step("Checking Redis service status...")
    result = run_ssh(ctx, "systemctl is-active redis-server", show=False, check=False)
    if "active" not in result.stdout:
        print_error("Redis service is not running")
        run_ssh(ctx, "systemctl status redis-server --no-pager", check=False)
        msg = "Redis service not running"
        raise RuntimeError(msg)
    print_success("Redis service is running")

    # Verify Redis is responding
    print_step("Verifying Redis is responding...")
    result = run_ssh(ctx, "redis-cli ping", show=False, check=False)
    if result.returncode != 0 or "PONG" not in result.stdout:
        print_error("Redis is not responding to ping")
        msg = "Redis not responding"
        raise RuntimeError(msg)
    print_success("Redis is responding")
