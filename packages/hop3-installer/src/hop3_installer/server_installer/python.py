# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Python virtual environment and package installation."""

from __future__ import annotations

import grp
import os
import pwd
import shlex
import shutil
import tempfile
from pathlib import Path

from hop3_installer.common import (
    CommandError,
    Spinner,
    print_info,
    print_success,
    print_warning,
)

from .config import (
    GIT_REPO,
    GIT_SUBDIR,
    HOP3_GROUP,
    HOP3_USER,
    PACKAGE_NAME,
    VENV_DIR,
    ServerInstallerConfig,
)
from .user import run_as_hop3


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
        Path(temp_keys).chmod(0o600)  # Restrict permissions

        # Run setup:ssh - quote the path for safety
        run_as_hop3(f"{hop_server} setup:ssh {shlex.quote(str(temp_keys))}")
        print_success("SSH keys configured")
    except CommandError:
        print_warning("Could not configure SSH keys (invalid format?)")
    finally:
        if temp_keys.exists():
            temp_keys.unlink()
