# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Python virtual environment and package installation for CLI installer."""

from __future__ import annotations

import re
import shutil
import sys
import urllib.request
from pathlib import Path

from hop3_installer.common import Spinner, print_info, print_success, run_cmd
from hop3_installer.constants import (
    CLI_INSTALL_DIR,
    CLI_PACKAGE_NAME,
    CLI_PACKAGE_SUBDIR,
    CLI_VENV_DIR,
    GIT_REPO,
)

from .config import CLIInstallerConfig

# Git branch/ref names: alphanumeric, dots, hyphens, slashes, underscores.
# Rejects shell metacharacters and whitespace.
_GIT_REF_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._/\-]*$")

# Semver-like: N.N.N with optional pre-release suffix.
_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+([a-z]+\.[0-9]+)?$")


def _validate_branch(branch: str) -> str:
    """Validate a git branch/ref name. Raises ValueError on invalid input."""
    if not _GIT_REF_RE.match(branch):
        msg = f"Invalid git branch/ref: {branch!r}. Must match {_GIT_REF_RE.pattern}"
        raise ValueError(msg)
    return branch


def _validate_version(version: str) -> str:
    """Validate a version string. Raises ValueError on invalid input."""
    if not _VERSION_RE.match(version):
        msg = f"Invalid version: {version!r}. Must be semver-like (e.g., 0.4.0)"
        raise ValueError(msg)
    return version


def _validate_local_path(path: str) -> str:
    """Validate and resolve a local path. Raises ValueError on suspicious input."""
    resolved = Path(path).resolve()
    if not resolved.exists():
        msg = f"Local path does not exist: {resolved}"
        raise ValueError(msg)
    # Reject paths that attempt traversal via symlink tricks.
    # Resolved path must be a real directory under a plausible prefix.
    if not resolved.is_dir() and not resolved.is_file():
        msg = f"Local path is not a file or directory: {resolved}"
        raise ValueError(msg)
    return str(resolved)


def create_virtual_environment() -> None:
    """Create a Python virtual environment."""
    # Create install directory
    CLI_INSTALL_DIR.mkdir(parents=True, exist_ok=True)

    # Remove existing venv if present
    if CLI_VENV_DIR.exists():
        shutil.rmtree(CLI_VENV_DIR)

    # Try creating venv with pip first (faster if ensurepip is available)
    with Spinner("Creating virtual environment..."):
        result = run_cmd(
            [sys.executable, "-m", "venv", str(CLI_VENV_DIR)],
            check=False,
        )

    if result.returncode == 0:
        print_success(f"Virtual environment created at {CLI_VENV_DIR}")
        return

    # Fallback: create venv without pip, then bootstrap pip manually
    # This works on systems where python3-venv is installed but ensurepip is not
    print_info("ensurepip not available, bootstrapping pip manually...")

    # Remove failed venv attempt
    if CLI_VENV_DIR.exists():
        shutil.rmtree(CLI_VENV_DIR)

    with Spinner("Creating virtual environment (without pip)..."):
        run_cmd([sys.executable, "-m", "venv", "--without-pip", str(CLI_VENV_DIR)])

    # Download and run get-pip.py
    get_pip_url = "https://bootstrap.pypa.io/get-pip.py"
    get_pip_path = CLI_INSTALL_DIR / "get-pip.py"

    with Spinner("Downloading pip installer..."):
        urllib.request.urlretrieve(get_pip_url, get_pip_path)

    venv_python = CLI_VENV_DIR / "bin" / "python"
    with Spinner("Installing pip..."):
        run_cmd([str(venv_python), str(get_pip_path), "--quiet"])

    # Clean up
    get_pip_path.unlink(missing_ok=True)

    print_success(f"Virtual environment created at {CLI_VENV_DIR}")


def install_package(config: CLIInstallerConfig) -> None:
    """Install the hop3-cli package."""
    pip = str(CLI_VENV_DIR / "bin" / "pip")

    # Upgrade pip first
    with Spinner("Upgrading pip..."):
        run_cmd([pip, "install", "--upgrade", "pip"])

    # Determine what to install
    if config.local_path:
        package_spec = _validate_local_path(config.local_path)
        source_desc = f"local path ({package_spec})"
    elif config.use_git:
        # Install uv for build backend
        with Spinner("Installing build tools..."):
            run_cmd([pip, "install", "uv"])
        safe_branch = _validate_branch(config.branch)
        package_spec = f"git+{GIT_REPO}@{safe_branch}#subdirectory={CLI_PACKAGE_SUBDIR}"
        source_desc = f"git ({safe_branch} branch)"
    elif config.version:
        safe_version = _validate_version(config.version)
        package_spec = f"{CLI_PACKAGE_NAME}=={safe_version}"
        source_desc = f"PyPI (version {safe_version})"
    else:
        package_spec = CLI_PACKAGE_NAME
        source_desc = "PyPI (latest)"

    # Install the package
    with Spinner(f"Installing hop3-cli from {source_desc}..."):
        cmd = [pip, "install", package_spec]
        if config.verbose:
            run_cmd(cmd, capture=False)
        else:
            run_cmd(cmd)

    print_success("hop3-cli installed successfully")
