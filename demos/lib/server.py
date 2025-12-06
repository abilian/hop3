# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Server setup and management for demos."""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING

from .commands import run_local, run_ssh
from .output import pause, print_error, print_info, print_step, print_success

if TYPE_CHECKING:
    from .context import DemoContext


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


def check_hop3_installed(ctx: DemoContext) -> bool:
    """Check if Hop3 is installed on the server."""
    print_step("Checking if Hop3 is installed...")
    result = run_ssh(ctx, "test -f /home/hop3/venv/bin/hop-server", show=False, check=False)
    if result.returncode == 0:
        print_success("Hop3 is installed")
        return True
    print_info("Hop3 is not installed")
    return False


def install_hop3(ctx: DemoContext) -> None:
    """Install Hop3 on the server."""
    if not ctx.installer_path.exists():
        print_error("Cannot find Hop3 installer.")
        sys.exit(1)

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
        run_ssh(ctx, "python3 /tmp/install-server.py --local-path /tmp/hop3-server --verbose")
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
        sys.exit(1)

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
        sys.exit(1)
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
            sys.exit(1)

        # Find the built wheel (uv build outputs to repo root's dist/)
        dist_dir = ctx.dist_path
        wheels = list(dist_dir.glob("hop3_server-*.whl"))
        if not wheels:
            print_error("No wheel file found after build.")
            sys.exit(1)
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
