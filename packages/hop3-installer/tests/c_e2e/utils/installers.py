# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Installer bundling utilities for E2E tests."""

from __future__ import annotations

from pathlib import Path

from hop3_installer.bundler import bundle_installer

__all__ = [
    "bundle_installers",
    "get_packages_dir",
]


def get_packages_dir() -> Path:
    """Get the path to the hop3 packages directory.

    Returns:
        Path to packages/ directory in the repository
    """
    # Navigate from this file to the packages directory
    # tests/c_e2e/utils/installers.py -> packages/hop3-installer/tests/c_e2e/utils/
    this_file = Path(__file__)
    packages_dir = this_file.parent.parent.parent.parent.parent.parent / "packages"
    return packages_dir


def bundle_installers(output_dir: Path) -> dict[str, Path]:
    """Generate bundled installer scripts.

    Args:
        output_dir: Directory to write installer files

    Returns:
        Dict with 'cli' and 'server' keys pointing to installer paths
    """
    # Generate CLI installer
    cli_content = bundle_installer("cli")
    cli_path = output_dir / "install-cli.py"
    cli_path.write_text(cli_content)
    cli_path.chmod(0o755)

    # Generate server installer
    server_content = bundle_installer("server")
    server_path = output_dir / "install-server.py"
    server_path.write_text(server_content)
    server_path.chmod(0o755)

    return {"cli": cli_path, "server": server_path}
