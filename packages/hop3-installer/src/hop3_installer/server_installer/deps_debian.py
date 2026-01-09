# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Debian/Ubuntu dependency installation."""

from __future__ import annotations

from .config import ServerInstallerConfig  # noqa: TC001
from .deps_common import (
    PackageSpec,
    install_base_packages,
    install_dotnet_sdk_debian,
    install_optional_packages,
)
from .redis import configure_redis

# =============================================================================
# Debian/Ubuntu Package Specification (Declarative)
# =============================================================================

DEBIAN_SPEC = PackageSpec(
    pkg_manager="apt-get",
    update_cmd=["apt-get", "update", "-q"],
    env_vars={"DEBIAN_FRONTEND": "noninteractive"},
    base_packages=[
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
        # Go toolchain
        "golang-go",
        # Elixir toolchain
        "elixir",
        "erlang",
        # PHP toolchain
        "php",
        "php-cli",
        "php-mbstring",
        "php-xml",
        "php-curl",
        "php-zip",
        "php-pgsql",
        "php-mysql",
        "php-intl",
        "composer",
        # Java toolchain
        "default-jdk",
        "maven",
        # Common utilities
        "curl",
        "wget",
        "rsync",
        "socat",
        # Development libraries
        "libjpeg-dev",
        "libpng-dev",
        "libwebp-dev",
        "libpq-dev",
        "libffi-dev",
        "libssl-dev",
    ],
    docker_packages=["docker.io", "docker-buildx", "docker-compose-v2"],
    mysql_packages=["mysql-server", "mysql-client", "libmysqlclient-dev"],
    redis_packages=["redis-server"],
    conditional_packages={"npm": "npm"},
)


# =============================================================================
# Installation Functions
# =============================================================================


def install_debian_deps(config: ServerInstallerConfig) -> None:
    """Install all Debian/Ubuntu dependencies (except Rust, which needs hop3 user)."""
    install_base_packages(DEBIAN_SPEC)
    install_optional_packages(config, DEBIAN_SPEC, configure_redis)
    install_dotnet_sdk_debian()
