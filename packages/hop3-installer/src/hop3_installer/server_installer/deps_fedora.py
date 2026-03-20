# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Fedora/RHEL dependency installation.

Handles different RHEL-family distributions:
- Fedora: Uses moby-engine from native repos
- Rocky Linux / AlmaLinux: Uses Docker CE from Docker's official repo
- CentOS Stream: Uses Docker CE from Docker's official repo
"""

from __future__ import annotations

from hop3_installer.common import (
    DistroInfo,
    detect_distro_info,
    print_detail,
    print_info,
    run_cmd,
)

from .config import ServerInstallerConfig
from .deps_common import (
    PackageSpec,
    install_base_packages,
    install_dotnet_sdk_fedora,
    install_node_global_packages,
    install_optional_packages,
)
from .redis import configure_redis

# =============================================================================
# Fedora/RHEL Package Specification (Declarative)
# =============================================================================

# Base packages common to all Fedora/RHEL-family distributions
# Note: Some packages have different names or availability between
# Fedora and RHEL clones (Rocky/AlmaLinux). Use _get_fedora_base_packages()
# to get the appropriate list.
FEDORA_COMMON_PACKAGES = [
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
    # Required for compiling native extensions (Ruby gems, etc.)
    # Provides hardened compiler specs used by Fedora-compiled Ruby
    "redhat-rpm-config",
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
    # Common utilities
    "curl",
    "wget",
    "rsync",
    "socat",
    "unzip",
    "openssl",
    # SSL/TLS certificates
    "certbot",  # Let's Encrypt ACME client
    # Development libraries
    "libjpeg-devel",
    "libpng-devel",
    "libwebp-devel",
    "libpq-devel",
    "libffi-devel",
    "openssl-devel",
]

# Packages available on Fedora but not in RHEL clone base repos
FEDORA_ONLY_PACKAGES = [
    # Ruby json gem (Ruby 3.4+)
    "rubygem-json",
    # Elixir toolchain (requires EPEL on RHEL clones)
    "elixir",
    "erlang",
    # PHP toolchain (RHEL clones have limited PHP packages in base repos)
    "php",
    "php-fpm",
    "php-cli",
    "php-mbstring",
    "php-xml",
    "php-curl",
    "php-zip",
    "php-pgsql",
    "php-mysqlnd",
    "php-intl",
    "php-gd",
    "php-ldap",
    "php-bcmath",
    "php-gmp",
    "php-pecl-redis",
    "composer",
    # Java 21 (Fedora 42+)
    "java-21-openjdk-devel",
    "maven",
]

# Packages for RHEL clones (Rocky 9, AlmaLinux 9)
# These distros have different package availability
RHEL_CLONE_PACKAGES = [
    # Java 17 is the default on RHEL 9 clones
    "java-17-openjdk-devel",
    "maven",
    # Ruby json gem (required for Sinatra/Rack apps)
    "rubygem-json",
    # PHP packages available in RHEL 9 base/appstream
    "php",
    "php-fpm",
    "php-cli",
    "php-mbstring",
    "php-xml",
    "php-curl",
    "php-pgsql",
    "php-mysqlnd",
    "php-intl",
    "php-gd",
    "php-bcmath",
]


def _is_rhel_clone(distro_info: DistroInfo) -> bool:
    """Check if this is a RHEL clone (Rocky, AlmaLinux, CentOS Stream).

    These distros don't have Docker in their native repos and need
    Docker's official CentOS repo.
    """
    rhel_clones = {"rocky", "almalinux", "centos", "rhel"}
    return distro_info.distro in rhel_clones


def _setup_epel_for_rhel(distro_info: DistroInfo) -> bool:
    """Set up EPEL and CRB repositories for RHEL-family distros.

    EPEL (Extra Packages for Enterprise Linux) provides packages like
    certbot that aren't in the base RHEL repos.

    CRB (CodeReady Builder) provides development packages like
    libyaml-devel that aren't in AppStream.

    Returns:
        True if repositories were set up successfully, False otherwise.
    """
    print_info("Enabling EPEL repository...")

    # Install EPEL release package
    result = run_cmd(["dnf", "install", "-y", "epel-release"], check=False)

    if result.returncode == 0:
        print_detail("EPEL repository enabled successfully")
    else:
        print_detail(f"Failed to enable EPEL: {result.stderr}")
        return False

    # Enable CRB (CodeReady Builder) repository for development packages
    print_info("Enabling CRB repository...")
    result = run_cmd(["/usr/bin/crb", "enable"], check=False)

    if result.returncode == 0:
        print_detail("CRB repository enabled successfully")
    else:
        # Try alternative method for older systems
        result = run_cmd(["dnf", "config-manager", "--set-enabled", "crb"], check=False)
        if result.returncode == 0:
            print_detail("CRB repository enabled via config-manager")
        else:
            print_detail(f"Warning: Failed to enable CRB: {result.stderr}")
            # Don't fail - some packages might still work

    return True


def _setup_docker_repo_for_rhel() -> bool:
    """Set up Docker's official repo for RHEL-family distros.

    Docker doesn't have a Rocky/AlmaLinux-specific repo, but the CentOS repo
    works for all RHEL clones.

    Returns:
        True if repo was set up successfully, False otherwise.
    """
    print_info("Adding Docker official repository for RHEL-family...")

    # Add Docker's CentOS repo (works for Rocky, AlmaLinux, CentOS Stream)
    result = run_cmd(
        [
            "dnf",
            "config-manager",
            "--add-repo",
            "https://download.docker.com/linux/centos/docker-ce.repo",
        ],
        check=False,
    )

    if result.returncode != 0:
        # dnf-plugins-core may not be installed
        print_detail("Installing dnf-plugins-core...")
        run_cmd(["dnf", "install", "-y", "dnf-plugins-core"], check=False)

        # Retry adding repo
        result = run_cmd(
            [
                "dnf",
                "config-manager",
                "--add-repo",
                "https://download.docker.com/linux/centos/docker-ce.repo",
            ],
            check=False,
        )

    if result.returncode == 0:
        print_detail("Docker repository added successfully")
        return True
    print_detail(f"Failed to add Docker repo: {result.stderr}")
    return False


def _get_fedora_docker_packages(distro_info: DistroInfo) -> list[str]:
    """Get Docker packages appropriate for the distro.

    Fedora has moby-engine in native repos.
    RHEL clones need Docker CE from Docker's official repo.
    """
    if _is_rhel_clone(distro_info):
        # Docker CE packages from Docker's official repo
        return [
            "docker-ce",
            "docker-ce-cli",
            "containerd.io",
            "docker-buildx-plugin",
            "docker-compose-plugin",
        ]
    # Fedora: Use moby-engine from native repos
    # moby-engine is the open-source Docker engine maintained by Fedora
    return [
        "moby-engine",
        "docker-compose",
    ]


def _get_fedora_base_packages(distro_info: DistroInfo) -> list[str]:
    """Get base packages appropriate for the distro.

    Fedora has more packages in its native repos.
    RHEL clones (Rocky, AlmaLinux) have a more limited base repo and need EPEL
    for some packages, which we don't enable by default.
    """
    packages = list(FEDORA_COMMON_PACKAGES)

    if _is_rhel_clone(distro_info):
        # RHEL clones have limited base repos
        packages.extend(RHEL_CLONE_PACKAGES)
    else:
        # Fedora has more packages available
        packages.extend(FEDORA_ONLY_PACKAGES)

    return packages


def _create_fedora_package_spec(distro_info: DistroInfo) -> PackageSpec:
    """Create a PackageSpec appropriate for the detected distro.

    Args:
        distro_info: Detected distribution information.

    Returns:
        PackageSpec configured for the specific distro.
    """
    docker_packages = _get_fedora_docker_packages(distro_info)
    base_packages = _get_fedora_base_packages(distro_info)

    # MySQL package name differs
    if _is_rhel_clone(distro_info):
        # RHEL clones use mariadb by default, mysql-server is not in base repos
        mysql_packages = ["mariadb-server", "mariadb-devel"]
    else:
        mysql_packages = ["mysql-server", "mysql-devel"]

    return PackageSpec(
        pkg_manager="dnf",
        update_cmd=None,  # dnf doesn't need explicit update
        env_vars={},
        # Prevent weak dependencies (similar to apt's --no-install-recommends)
        install_flags=["--setopt=install_weak_deps=False"],
        base_packages=base_packages,
        docker_packages=docker_packages,
        mysql_packages=mysql_packages,
        redis_packages=["redis"],
        conditional_packages={"npm": "npm"},
    )


# =============================================================================
# Installation Functions
# =============================================================================


def install_fedora_deps(config: ServerInstallerConfig) -> None:
    """Install all Fedora/RHEL dependencies.

    Detects the specific distro and configures package sources accordingly.
    For RHEL clones (Rocky, AlmaLinux), sets up EPEL and Docker's official repo.
    """
    # Detect distro version
    distro_info = detect_distro_info()
    print_info(f"Detected: {distro_info}")

    # Set up EPEL for RHEL clones (needed for certbot, etc.)
    if _is_rhel_clone(distro_info):
        _setup_epel_for_rhel(distro_info)

    # Set up Docker repo for RHEL clones if Docker is requested
    if config.with_docker and _is_rhel_clone(distro_info):
        _setup_docker_repo_for_rhel()

    # Create version-appropriate package spec
    spec = _create_fedora_package_spec(distro_info)

    # Log Docker packages being installed
    print_detail(f"Docker packages: {', '.join(spec.docker_packages)}")

    # Install packages
    install_base_packages(spec)
    install_optional_packages(config, spec, configure_redis)
    install_dotnet_sdk_fedora()
    install_node_global_packages()
