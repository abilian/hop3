# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Fedora/RHEL dependency installation."""

from __future__ import annotations

from .config import ServerInstallerConfig  # noqa: TC001
from .deps_common import (
    PackageSpec,
    install_base_packages,
    install_dotnet_sdk_fedora,
    install_optional_packages,
)
from .redis import configure_redis

# =============================================================================
# Fedora/RHEL Package Specification (Declarative)
# =============================================================================

FEDORA_SPEC = PackageSpec(
    pkg_manager="dnf",
    update_cmd=None,  # dnf doesn't need explicit update
    env_vars={},
    base_packages=[
        # Core utilities
        "bc",
        "git",
        "sudo",
        "cronie",
        "gcc",
        "gcc-c++",
        "make",
        "pcre-devel",
        "zlib-devel",
        # Web server and database
        "nginx",
        "postgresql-server",
        "postgresql-contrib",
        # Python toolchain
        "python3-devel",
        "python3-pip",
        "python3-setuptools",
        # Node.js toolchain
        "nodejs",
        # Ruby toolchain
        "ruby",
        "ruby-devel",
        "rubygem-bundler",
        "libyaml-devel",
        "gmp-devel",
        # Go toolchain
        "golang",
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
        "php-mysqlnd",
        "php-intl",
        "composer",
        # Java toolchain
        "java-17-openjdk-devel",
        "maven",
        # Common utilities
        "curl",
        "wget",
        "rsync",
        "socat",
        "openssl",
        # Development libraries
        "libjpeg-devel",
        "libpng-devel",
        "libwebp-devel",
        "libpq-devel",
        "libffi-devel",
        "openssl-devel",
    ],
    docker_packages=["docker", "docker-buildx-plugin", "docker-compose-plugin"],
    mysql_packages=["mysql-server", "mysql-devel"],
    redis_packages=["redis"],
    conditional_packages={"npm": "npm"},
)


# =============================================================================
# Installation Functions
# =============================================================================


def install_fedora_deps(config: ServerInstallerConfig) -> None:
    """Install all Fedora/RHEL dependencies (except Rust, which needs hop3 user)."""
    install_base_packages(FEDORA_SPEC)
    install_optional_packages(config, FEDORA_SPEC, configure_redis)
    install_dotnet_sdk_fedora()
