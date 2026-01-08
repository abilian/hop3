# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""CLI argument parsing for CLI installer."""

from __future__ import annotations

import argparse
from pathlib import Path

from .config import DEFAULT_BIN_DIR, DEFAULT_BRANCH, CLIInstallerConfig

TOTAL_STEPS = 5


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    # Get defaults from environment
    env_config = CLIInstallerConfig.from_env()

    parser = argparse.ArgumentParser(
        prog="install-cli.py",
        description="Install the Hop3 CLI tool.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 install-cli.py                    Install latest version from PyPI
  python3 install-cli.py --git              Install from git (main branch)
  python3 install-cli.py --git --branch dev Install from git (dev branch)
  python3 install-cli.py --version 0.4.0    Install specific version
  python3 install-cli.py --force            Force reinstall

Environment Variables:
  HOP3_VERSION          Install specific version
  HOP3_GIT              Install from git (1 or true)
  HOP3_BRANCH           Git branch (default: main)
  HOP3_LOCAL_PACKAGE    Install from local path
  HOP3_FORCE            Force reinstall (1 or true)
  HOP3_NO_MODIFY_PATH   Don't modify shell config (1 or true)
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
        "--bin-dir",
        metavar="PATH",
        type=Path,
        default=env_config.bin_dir,
        help=f"Directory for command symlinks (default: {DEFAULT_BIN_DIR})",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        default=env_config.force,
        help="Force reinstall even if already installed",
    )

    parser.add_argument(
        "--no-modify-path",
        action="store_true",
        default=env_config.no_modify_path,
        help="Don't modify shell configuration files",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        default=env_config.verbose,
        help="Show verbose output",
    )

    return parser


def config_from_args(args: argparse.Namespace) -> CLIInstallerConfig:
    """Create CLIInstallerConfig from parsed arguments."""
    return CLIInstallerConfig(
        version=args.version,
        use_git=args.git,
        branch=args.branch,
        local_path=args.local_path,
        bin_dir=args.bin_dir,
        force=args.force,
        no_modify_path=args.no_modify_path,
        verbose=args.verbose,
    )
