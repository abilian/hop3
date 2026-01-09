# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Hop3 CLI Installer - Main orchestration.

A single-file installer for the Hop3 CLI tool.
Uses only Python standard library for maximum portability.

Usage:
    curl -LsSf https://hop3.cloud/install-cli.py | python3 -
    curl -LsSf https://hop3.cloud/install-cli.py | python3 - --git
    python3 install-cli.py --help
"""

from __future__ import annotations

import sys

from hop3_installer.common import (
    Colors,
    CommandError,
    check_python_version,
    print_detail,
    print_error,
    print_header,
    print_info,
    print_step,
    print_warning,
)

from .checks import check_existing_installation, check_system_requirements
from .cli import TOTAL_STEPS, config_from_args, create_parser
from .python import create_virtual_environment, install_package
from .shell import create_command_symlinks, update_shell_config
from .verify import print_final_message, verify_installation

# =============================================================================
# Error Handling
# =============================================================================


def _handle_venv_creation_error(e: CommandError) -> None:
    """Handle virtual environment creation error with helpful output."""
    print_error("Failed to create virtual environment")
    error_output = e.stderr.strip() or e.stdout.strip()
    if error_output:
        for line in error_output.split("\n"):
            if line.strip():
                print_detail(line.strip())
    else:
        print_detail(f"Command: {' '.join(e.cmd)}")
        print_detail(f"Exit code: {e.returncode}")
    print()
    print_info("Possible fixes:")
    print_detail("1. Check disk space: df -h ~/.hop3-cli")
    print_detail("2. Check permissions: ls -la ~/.hop3-cli")
    print_detail("3. Check network access (needed to download pip)")


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
    config = config_from_args(args)

    print_header("Hop3 CLI Installer")

    # Step 1: System checks
    print_step(1, TOTAL_STEPS, "Checking system requirements...")
    if not check_system_requirements(config):
        return 1

    # Check existing installation
    if not check_existing_installation(force=config.force):
        return 0

    # Step 2: Create virtual environment
    print_step(2, TOTAL_STEPS, "Creating virtual environment...")
    try:
        create_virtual_environment()
    except CommandError as e:
        _handle_venv_creation_error(e)
        return 1

    # Step 3: Install package
    print_step(3, TOTAL_STEPS, "Installing hop3-cli...")
    try:
        install_package(config)
    except CommandError as e:
        print_error("Failed to install hop3-cli")
        if config.verbose:
            print_detail(e.stderr)
        if config.use_git:
            print_detail("Make sure git is installed and you have network access")
        else:
            print_detail("Try --git to install from the git repository")
        return 1

    # Step 4: Create symlinks
    print_step(4, TOTAL_STEPS, "Creating command symlinks...")
    count = create_command_symlinks(config.bin_dir)
    if count == 0:
        print_warning("No commands found to symlink")

    # Step 5: Update PATH
    print_step(5, TOTAL_STEPS, "Configuring PATH...")
    path_is_active = update_shell_config(
        config.bin_dir, modify_path=not config.no_modify_path
    )

    # Verify
    print()
    if not verify_installation():
        print_warning("Installation may have issues")

    # Success message
    print_final_message(config.bin_dir, path_is_active=path_is_active)

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
