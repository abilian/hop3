# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""System checks for CLI installer."""

from __future__ import annotations

import importlib.util
import sys

from hop3_installer.common import (
    cmd_exists,
    print_detail,
    print_error,
    print_info,
    print_success,
)
from hop3_installer.constants import CLI_INSTALL_DIR, CLI_VENV_DIR

from .config import CLIInstallerConfig


def check_venv() -> bool:
    """
    Check that ``python -m venv`` can work: ``venv``, and the ``ensurepip`` it needs.

    Debian ships ``venv`` without ``ensurepip`` until python3-venv is installed.
    Looked up, not imported: the bundler hoists every import to the top of the
    single file, which made an ``import venv`` here always succeed.
    """
    return all(importlib.util.find_spec(m) for m in ("venv", "ensurepip"))


def check_git() -> bool:
    """Check if git is available."""
    return cmd_exists("git")


def check_existing_installation(*, force: bool) -> bool:
    """
    Check for existing installation.

    Returns:
        True if should proceed with installation, False if already installed
    """
    if CLI_VENV_DIR.exists():
        if force:
            print_info("Existing installation found, will reinstall (--clean)")
            return True
        print_info("Hop3 CLI is already installed")
        print_detail(f"Location: {CLI_INSTALL_DIR}")
        print_detail("Use --clean to reinstall")
        return False
    return True


def check_system_requirements(config: CLIInstallerConfig) -> bool:
    """
    Check system requirements for CLI installation.

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
