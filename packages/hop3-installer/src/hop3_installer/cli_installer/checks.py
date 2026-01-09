# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""System checks for CLI installer."""

from __future__ import annotations

import sys

from hop3_installer.common import (
    cmd_exists,
    print_detail,
    print_error,
    print_info,
    print_success,
    print_warning,
)

from .config import INSTALL_DIR, VENV_DIR, CLIInstallerConfig


def check_venv() -> bool:
    """Check if venv module is available."""
    try:
        import venv  # noqa: F401

        return True
    except ImportError:
        return False


def check_git() -> bool:
    """Check if git is available."""
    return cmd_exists("git")


def check_existing_installation(*, force: bool) -> bool:
    """Check for existing installation.

    Returns:
        True if should proceed with installation, False if already installed
    """
    if VENV_DIR.exists():
        if force:
            print_info("Existing installation found, will reinstall (--force)")
            return True
        print_warning("Hop3 CLI is already installed")
        print_detail(f"Location: {INSTALL_DIR}")
        print_detail("Use --force to reinstall")
        return False
    return True


def check_system_requirements(config: CLIInstallerConfig) -> bool:
    """Check system requirements for CLI installation.

    Returns:
        True if requirements met, False otherwise.
    """
    python_version = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    print_success(f"Python {python_version}")

    if not check_venv():
        print_error("Python venv module not found")
        print_detail("Install with: sudo apt install python3-venv")
        return False
    print_success("venv module available")

    if config.use_git and not config.local_path and not check_git():
        print_error("Git not found (required for --git)")
        print_detail("Install with: sudo apt install git")
        return False

    return True
