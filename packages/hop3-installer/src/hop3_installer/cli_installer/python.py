# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Python virtual environment and package installation for CLI installer."""

from __future__ import annotations

import shutil
import sys
import urllib.request

from hop3_installer.common import Spinner, print_info, print_success, run_cmd

from .config import (
    GIT_REPO,
    GIT_SUBDIR,
    INSTALL_DIR,
    PACKAGE_NAME,
    VENV_DIR,
    CLIInstallerConfig,
)


def create_virtual_environment() -> None:
    """Create a Python virtual environment."""
    # Create install directory
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)

    # Remove existing venv if present
    if VENV_DIR.exists():
        shutil.rmtree(VENV_DIR)

    # Try creating venv with pip first (faster if ensurepip is available)
    with Spinner("Creating virtual environment..."):
        result = run_cmd(
            [sys.executable, "-m", "venv", str(VENV_DIR)],
            check=False,
        )

    if result.returncode == 0:
        print_success(f"Virtual environment created at {VENV_DIR}")
        return

    # Fallback: create venv without pip, then bootstrap pip manually
    # This works on systems where python3-venv is installed but ensurepip is not
    print_info("ensurepip not available, bootstrapping pip manually...")

    # Remove failed venv attempt
    if VENV_DIR.exists():
        shutil.rmtree(VENV_DIR)

    with Spinner("Creating virtual environment (without pip)..."):
        run_cmd([sys.executable, "-m", "venv", "--without-pip", str(VENV_DIR)])

    # Download and run get-pip.py
    get_pip_url = "https://bootstrap.pypa.io/get-pip.py"
    get_pip_path = INSTALL_DIR / "get-pip.py"

    with Spinner("Downloading pip installer..."):
        urllib.request.urlretrieve(get_pip_url, get_pip_path)

    venv_python = VENV_DIR / "bin" / "python"
    with Spinner("Installing pip..."):
        run_cmd([str(venv_python), str(get_pip_path), "--quiet"])

    # Clean up
    get_pip_path.unlink(missing_ok=True)

    print_success(f"Virtual environment created at {VENV_DIR}")


def install_package(config: CLIInstallerConfig) -> None:
    """Install the hop3-cli package."""
    pip = str(VENV_DIR / "bin" / "pip")

    # Upgrade pip first
    with Spinner("Upgrading pip..."):
        run_cmd([pip, "install", "--upgrade", "pip"])

    # Determine what to install
    if config.local_path:
        package_spec = config.local_path
        source_desc = f"local path ({config.local_path})"
    elif config.use_git:
        # Install uv for build backend
        with Spinner("Installing build tools..."):
            run_cmd([pip, "install", "uv"])
        package_spec = f"git+{GIT_REPO}@{config.branch}#subdirectory={GIT_SUBDIR}"
        source_desc = f"git ({config.branch} branch)"
    elif config.version:
        package_spec = f"{PACKAGE_NAME}=={config.version}"
        source_desc = f"PyPI (version {config.version})"
    else:
        package_spec = PACKAGE_NAME
        source_desc = "PyPI (latest)"

    # Install the package
    with Spinner(f"Installing hop3-cli from {source_desc}..."):
        cmd = [pip, "install", package_spec]
        if config.verbose:
            run_cmd(cmd, capture=False)
        else:
            run_cmd(cmd)

    print_success("hop3-cli installed successfully")
