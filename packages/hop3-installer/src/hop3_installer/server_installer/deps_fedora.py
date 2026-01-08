# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Fedora/RHEL dependency installation."""

from __future__ import annotations

from hop3_installer.common import (
    CommandError,
    Spinner,
    cmd_exists,
    print_detail,
    print_error,
    print_success,
    print_warning,
    run_cmd,
)

from .config import ServerInstallerConfig  # noqa: TC001
from .deps_common import (
    PackageSpec,
    install_dotnet_sdk_fedora,
    install_rust_toolchain,
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
    """Install all Fedora/RHEL dependencies."""
    _install_base_packages()
    _install_optional_packages(config)
    install_dotnet_sdk_fedora()
    install_rust_toolchain()


def _install_base_packages() -> None:
    """Install base Fedora/RHEL packages."""
    spec = FEDORA_SPEC

    # Install base packages
    with Spinner("Installing base packages (this may take a while)..."):
        result = run_cmd(
            [spec.pkg_manager, "install", "-y"] + spec.base_packages,
            check=False,
        )

    if result.returncode != 0:
        print_error("Base package installation failed")
        if result.stderr:
            for line in result.stderr.strip().split("\n")[-10:]:
                print_detail(line)
        raise CommandError(
            [spec.pkg_manager, "install"] + spec.base_packages,
            result.returncode,
            result.stderr or "",
        )

    print_success(f"Installed {len(spec.base_packages)} base packages")

    # Handle conditional packages
    for cmd_name, pkg_name in spec.conditional_packages.items():
        _install_conditional_package(cmd_name, pkg_name, spec)


def _install_conditional_package(
    cmd_name: str, pkg_name: str, spec: PackageSpec
) -> None:
    """Install a package only if the command doesn't already exist."""
    if cmd_exists(cmd_name):
        print_success(f"{cmd_name} already available")
        return

    with Spinner(f"Installing {pkg_name}..."):
        result = run_cmd(
            [spec.pkg_manager, "install", "-y", pkg_name],
            check=False,
        )
    if result.returncode == 0:
        print_success(f"{pkg_name} installed")
    else:
        print_warning(f"{pkg_name} installation failed")


def _install_optional_packages(config: ServerInstallerConfig) -> None:
    """Install optional Fedora/RHEL packages based on config."""
    spec = FEDORA_SPEC

    if config.with_docker:
        _install_feature_packages("Docker", spec.docker_packages, spec)

    if config.with_mysql:
        if not cmd_exists("mysql"):
            _install_feature_packages("MySQL", spec.mysql_packages, spec)
        else:
            print_success("MySQL already installed")

    if config.with_redis:
        if not cmd_exists("redis-server"):
            _install_feature_packages("Redis", spec.redis_packages, spec)
        else:
            print_success("Redis already installed")
        configure_redis()


def _install_feature_packages(
    name: str, packages: list[str], spec: PackageSpec
) -> None:
    """Install a set of feature packages."""
    with Spinner(f"Installing {name} packages..."):
        result = run_cmd(
            [spec.pkg_manager, "install", "-y"] + packages,
            check=False,
        )
    if result.returncode == 0:
        print_success(f"{name} packages installed")
    else:
        print_warning(f"{name} installation failed")
        if result.stderr:
            for line in result.stderr.strip().split("\n")[-5:]:
                print_detail(line)
