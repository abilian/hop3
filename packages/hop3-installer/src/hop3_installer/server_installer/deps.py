# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""System dependency installation dispatcher.

This module dispatches to distro-specific modules for package installation.
"""

from __future__ import annotations

from hop3_installer.common import print_detail, print_info, print_warning

from .config import ServerInstallerConfig  # noqa: TC001
from .deps_debian import install_debian_deps
from .deps_fedora import install_fedora_deps


def install_system_deps(distro: str, config: ServerInstallerConfig) -> None:
    """Install system dependencies for the detected distribution.

    Args:
        distro: Distribution name ("debian", "fedora", or "unknown")
        config: Server installer configuration
    """
    if config.skip_deps:
        print_info("Skipping system dependencies (--skip-deps)")
        return

    if distro == "debian":
        install_debian_deps(config)
    elif distro == "fedora":
        install_fedora_deps(config)
    else:
        print_warning(f"Unknown distro '{distro}', skipping package installation")
        print_detail("You may need to install dependencies manually")
