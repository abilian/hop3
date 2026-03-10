# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Debian/Ubuntu dependency installation.

Handles version-specific package differences:
- Debian 12 (bookworm): Uses trixie repo for newer Go
- Debian 13 (trixie): Uses native packages
- Ubuntu 24.04+: Uses native packages
- Older versions: May need PPAs or backports
"""

from __future__ import annotations

from pathlib import Path

from hop3_installer.common import (
    DistroInfo,
    detect_distro_info,
    print_detail,
    print_info,
)

from .config import ServerInstallerConfig  # noqa: TC001
from .deps_common import (
    PackageSpec,
    install_base_packages,
    install_dotnet_sdk_debian,
    install_node_global_packages,
    install_optional_packages,
)
from .redis import configure_redis

# =============================================================================
# Debian/Ubuntu Package Specification (Declarative)
# =============================================================================

# Base packages common to all Debian/Ubuntu versions
BASE_PACKAGES = [
    # Core utilities
    "bc",
    "git",
    "sudo",
    "cron",
    "build-essential",
    "libpcre3-dev",
    "zlib1g-dev",
    # Web server and database
    "nginx",
    "postgresql",
    "postgresql-contrib",
    # Python toolchain
    "python3-dev",
    "python3-pip",
    "python3-venv",
    "python3-setuptools",
    # Node.js toolchain
    "nodejs",
    # Ruby toolchain
    "ruby",
    "ruby-dev",
    "ruby-bundler",
    "libyaml-dev",
    "libgmp-dev",
    # Go toolchain (version handled separately for older distros)
    "golang-go",
    # Elixir toolchain
    "elixir",
    "erlang",
    # PHP toolchain (using php-fpm for Nginx, not mod_php for Apache)
    "php",
    "php-fpm",
    "php-cli",
    "php-mbstring",
    "php-xml",
    "php-curl",
    "php-zip",
    "php-pgsql",
    "php-mysql",
    "php-intl",
    "php-gd",
    "php-ldap",
    "php-bcmath",
    "php-gmp",
    "php-redis",
    "composer",
    # Java toolchain
    "default-jdk",
    "maven",
    # Common utilities
    "curl",
    "wget",
    "rsync",
    "socat",
    "unzip",
    # SSL/TLS certificates
    "certbot",
    # Development libraries
    "libjpeg-dev",
    "libpng-dev",
    "libwebp-dev",
    "libpq-dev",
    "libffi-dev",
    "libssl-dev",
]


def _create_package_spec(distro_info: DistroInfo) -> PackageSpec:
    """Create a PackageSpec appropriate for the detected distro version.

    Args:
        distro_info: Detected distribution information.

    Returns:
        PackageSpec configured for the specific distro/version.
    """
    packages = list(BASE_PACKAGES)

    # Version-specific adjustments are handled in _setup_package_sources()
    # This function just returns the base spec

    return PackageSpec(
        pkg_manager="apt-get",
        update_cmd=["apt-get", "update", "-q"],
        env_vars={"DEBIAN_FRONTEND": "noninteractive"},
        install_flags=["--no-install-recommends"],
        base_packages=packages,
        docker_packages=["docker.io", "docker-cli", "docker-compose"],
        mysql_packages=["mysql-server", "mysql-client", "libmysqlclient-dev"],
        redis_packages=["redis-server"],
        conditional_packages={"npm": "npm"},
    )


def _setup_package_sources(distro_info: DistroInfo) -> None:
    """Configure additional package sources based on distro version.

    For older distributions that lack recent package versions, this adds
    appropriate additional repositories.

    Args:
        distro_info: Detected distribution information.
    """
    # Debian 12 (bookworm): Add trixie repo for newer packages (Go 1.23, etc.)
    if distro_info.is_debian and distro_info.codename == "bookworm":
        print_info("Debian 12 detected: adding trixie repository for newer packages")
        trixie_list = Path("/etc/apt/sources.list.d/trixie.list")
        trixie_content = "deb http://deb.debian.org/debian trixie main\n"

        if not trixie_list.exists():
            trixie_list.write_text(trixie_content)
            print_detail(f"Created {trixie_list}")

    # Ubuntu versions before 24.04 might need PPAs for newer Go
    # (Currently Ubuntu 24.04+ has Go 1.22+ which is sufficient)
    elif distro_info.is_ubuntu and distro_info.version_major < 24:
        print_info(f"Ubuntu {distro_info.version} detected: older Go version may be used")
        print_detail("Consider upgrading to Ubuntu 24.04+ for best compatibility")

    # Debian 11 (bullseye) is quite old - warn user
    elif distro_info.is_debian and distro_info.codename == "bullseye":
        print_info("Debian 11 detected: adding trixie repository for newer packages")
        trixie_list = Path("/etc/apt/sources.list.d/trixie.list")
        trixie_content = "deb http://deb.debian.org/debian trixie main\n"

        if not trixie_list.exists():
            trixie_list.write_text(trixie_content)
            print_detail(f"Created {trixie_list}")


# =============================================================================
# Installation Functions
# =============================================================================


def install_debian_deps(config: ServerInstallerConfig) -> None:
    """Install all Debian/Ubuntu dependencies.

    Detects the specific distro version and configures package sources
    accordingly before installing packages.

    Args:
        config: Server installer configuration.
    """
    # Detect distro version
    distro_info = detect_distro_info()
    print_info(f"Detected: {distro_info}")

    # Setup additional package sources if needed (e.g., trixie for Debian 12)
    _setup_package_sources(distro_info)

    # Create version-appropriate package spec
    spec = _create_package_spec(distro_info)

    # Install packages
    install_base_packages(spec)
    install_optional_packages(config, spec, configure_redis)
    install_dotnet_sdk_debian()
    install_node_global_packages()
