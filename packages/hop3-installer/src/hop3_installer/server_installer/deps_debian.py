# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Debian/Ubuntu dependency installation."""

from __future__ import annotations

from hop3_installer.common import (
    CommandError,
    Spinner,
    cmd_exists,
    print_detail,
    print_error,
    print_info,
    print_success,
    print_warning,
    run_cmd,
)

from .config import ServerInstallerConfig  # noqa: TC001
from .deps_common import (
    PackageSpec,
    install_dotnet_sdk_debian,
    install_rust_toolchain,
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
    """Install all Debian/Ubuntu dependencies."""
    _install_base_packages()
    _install_optional_packages(config)
    install_dotnet_sdk_debian()
    install_rust_toolchain()


def _install_base_packages() -> None:
    """Install base Debian/Ubuntu packages."""
    spec = DEBIAN_SPEC

    # Update package lists
    if spec.update_cmd:
        with Spinner("Updating package lists..."):
            run_cmd(spec.update_cmd)

    # Install base packages
    with Spinner("Installing base packages (this may take a while)..."):
        result = run_cmd(
            [spec.pkg_manager, "install", "-y"] + spec.base_packages,
            env=spec.env_vars,
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

    # Handle conditional packages (packages that may conflict)
    for cmd_name, pkg_name in spec.conditional_packages.items():
        _install_conditional_package(cmd_name, pkg_name, spec)


def _install_conditional_package(
    cmd_name: str, pkg_name: str, spec: PackageSpec
) -> None:
    """Install a package only if the command doesn't already exist."""
    if cmd_exists(cmd_name):
        print_success(f"{cmd_name} already available")
        return

    print_info(f"{cmd_name} not found, installing {pkg_name}...")
    with Spinner(f"Installing {pkg_name}..."):
        result = run_cmd(
            [spec.pkg_manager, "install", "-y", pkg_name],
            env=spec.env_vars,
            check=False,
        )
    if result.returncode == 0:
        print_success(f"{pkg_name} installed")
    else:
        print_warning(
            f"{pkg_name} installation failed (may conflict with other packages)"
        )


def _install_optional_packages(config: ServerInstallerConfig) -> None:
    """Install optional Debian/Ubuntu packages based on config."""
    spec = DEBIAN_SPEC

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
            env=spec.env_vars,
            check=False,
        )
    if result.returncode == 0:
        print_success(f"{name} packages installed")
    else:
        print_warning(f"{name} installation failed")
        if result.stderr:
            for line in result.stderr.strip().split("\n")[-5:]:
                print_detail(line)
