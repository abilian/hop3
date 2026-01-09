# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Common dependency installation utilities shared across distros."""

from __future__ import annotations

from collections.abc import Callable  # noqa: TC003
from dataclasses import dataclass, field
from pathlib import Path

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

from .config import HOME_DIR, ServerInstallerConfig
from .user import run_as_hop3

# =============================================================================
# Declarative Package Specification
# =============================================================================


@dataclass
class PackageSpec:
    """Declarative specification for packages to install.

    This enables a more data-driven approach to package installation,
    making it easier to maintain and extend package lists.
    """

    # Package manager configuration
    pkg_manager: str  # "apt-get" or "dnf"
    update_cmd: list[str] | None = None  # Command to update package lists
    env_vars: dict[str, str] = field(default_factory=dict)

    # Package lists
    base_packages: list[str] = field(default_factory=list)
    docker_packages: list[str] = field(default_factory=list)
    mysql_packages: list[str] = field(default_factory=list)
    redis_packages: list[str] = field(default_factory=list)

    # Commands that need special handling (check before install)
    conditional_packages: dict[str, str] = field(default_factory=dict)
    # Maps command name -> package name, e.g., {"npm": "npm"}


# =============================================================================
# Shared Package Installation Functions
# =============================================================================


def install_base_packages(spec: PackageSpec) -> None:
    """Install base packages using the given spec."""
    # Update package lists if needed
    if spec.update_cmd:
        with Spinner("Updating package lists..."):
            run_cmd(spec.update_cmd)

    # Install base packages
    with Spinner("Installing base packages (this may take a while)..."):
        result = run_cmd(
            [spec.pkg_manager, "install", "-y"] + spec.base_packages,
            env=spec.env_vars if spec.env_vars else None,
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
        install_conditional_package(cmd_name, pkg_name, spec)


def install_conditional_package(
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
            env=spec.env_vars if spec.env_vars else None,
            check=False,
        )
    if result.returncode == 0:
        print_success(f"{pkg_name} installed")
    else:
        print_warning(
            f"{pkg_name} installation failed (may conflict with other packages)"
        )


def install_optional_packages(
    config: ServerInstallerConfig,
    spec: PackageSpec,
    configure_redis_func: Callable[[], None],
) -> None:
    """Install optional packages based on config."""
    if config.with_docker:
        install_feature_packages("Docker", spec.docker_packages, spec)

    if config.with_mysql:
        if not cmd_exists("mysql"):
            install_feature_packages("MySQL", spec.mysql_packages, spec)
        else:
            print_success("MySQL already installed")

    if config.with_redis:
        if not cmd_exists("redis-server"):
            install_feature_packages("Redis", spec.redis_packages, spec)
        else:
            print_success("Redis already installed")
        configure_redis_func()


def install_feature_packages(name: str, packages: list[str], spec: PackageSpec) -> None:
    """Install a set of feature packages."""
    with Spinner(f"Installing {name} packages..."):
        result = run_cmd(
            [spec.pkg_manager, "install", "-y"] + packages,
            env=spec.env_vars if spec.env_vars else None,
            check=False,
        )
    if result.returncode == 0:
        print_success(f"{name} packages installed")
    else:
        print_warning(f"{name} installation failed")
        if result.stderr:
            for line in result.stderr.strip().split("\n")[-5:]:
                print_detail(line)


# =============================================================================
# Rust Toolchain
# =============================================================================


def install_rust_toolchain() -> None:
    """Install Rust toolchain via rustup.

    Rust is installed using rustup, which manages the Rust toolchain.
    This is installed for the hop3 user so apps can be built.
    Symlinks are created in /usr/local/bin for system-wide access.
    """
    cargo_path = HOME_DIR / ".cargo" / "bin" / "cargo"
    rustc_path = HOME_DIR / ".cargo" / "bin" / "rustc"
    rustup_path = HOME_DIR / ".cargo" / "bin" / "rustup"

    # Check if cargo actually works for the hop3 user
    if cargo_path.exists():
        result = run_as_hop3(f"{cargo_path} --version")
        if result.returncode == 0:
            print_info(f"Rust toolchain already installed: {result.stdout.strip()}")
            # Ensure symlinks exist
            _create_rust_symlinks(cargo_path, rustc_path, rustup_path)
            return

    print_info("Installing Rust toolchain via rustup...")

    # Remove any broken symlinks first
    for symlink in [
        "/usr/local/bin/cargo",
        "/usr/local/bin/rustc",
        "/usr/local/bin/rustup",
    ]:
        symlink_path = Path(symlink)
        if symlink_path.is_symlink() and not symlink_path.exists():
            print_detail(f"Removing broken symlink: {symlink}")
            symlink_path.unlink()

    # Install rustup for the hop3 user
    with Spinner("Downloading and installing rustup..."):
        result = run_as_hop3(
            'curl --proto "=https" --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y'
        )

    if result.returncode != 0:
        print_warning("Rust installation failed")
        if result.stderr:
            print_detail(result.stderr[:200])
        return

    # Verify installation
    if cargo_path.exists():
        print_success("Rust toolchain installed")
        # Show version
        result = run_as_hop3(f"{cargo_path} --version")
        if result.returncode == 0:
            print_detail(f"Version: {result.stdout.strip()}")

        # Create system-wide symlinks
        _create_rust_symlinks(cargo_path, rustc_path, rustup_path)
    else:
        print_warning("Rust installation completed but cargo not found")


def _create_rust_symlinks(
    cargo_path: Path, rustc_path: Path, rustup_path: Path
) -> None:
    """Create symlinks in /usr/local/bin for Rust tools.

    This makes cargo, rustc, and rustup accessible system-wide,
    which is needed when subprocess runs commands without the hop3 user's PATH.
    """
    symlinks = [
        (cargo_path, Path("/usr/local/bin/cargo")),
        (rustc_path, Path("/usr/local/bin/rustc")),
        (rustup_path, Path("/usr/local/bin/rustup")),
    ]

    for source, target in symlinks:
        if not source.exists():
            continue

        # Remove existing symlink or file
        if target.exists() or target.is_symlink():
            target.unlink()

        try:
            target.symlink_to(source)
            print_detail(f"Created symlink: {target} -> {source}")
        except OSError as e:
            print_warning(f"Could not create symlink {target}: {e}")


# =============================================================================
# .NET SDK
# =============================================================================


def _detect_debian_version() -> tuple[str, str]:
    """Detect Debian/Ubuntu version for Microsoft repo URL.

    Returns:
        Tuple of (distro, version) e.g., ("ubuntu", "24.04") or ("debian", "12")
    """
    # Try /etc/os-release first (works on most modern systems)
    os_release = Path("/etc/os-release")
    if os_release.exists():
        content = os_release.read_text()
        distro = ""
        version = ""
        for line in content.split("\n"):
            if line.startswith("ID="):
                distro = line.split("=")[1].strip().strip('"').lower()
            elif line.startswith("VERSION_ID="):
                version = line.split("=")[1].strip().strip('"')
        if distro and version:
            return (distro, version)

    # Fallback to Ubuntu 24.04 as default
    return ("ubuntu", "24.04")


def install_dotnet_sdk_debian() -> None:
    """Install .NET SDK on Debian/Ubuntu from Microsoft repository."""
    if cmd_exists("dotnet"):
        print_info(".NET SDK already installed")
        return

    # Detect the actual OS version
    distro, version = _detect_debian_version()
    print_detail(f"Detected {distro} {version}")

    # Microsoft provides packages for specific distro/version combinations
    # See: https://learn.microsoft.com/en-us/dotnet/core/install/linux
    repo_url = (
        f"https://packages.microsoft.com/config/{distro}/{version}/"
        "packages-microsoft-prod.deb"
    )

    # Add Microsoft package repository for Debian/Ubuntu
    with Spinner("Adding Microsoft package repository..."):
        # Download and install the Microsoft package signing key
        result = run_cmd(
            ["wget", "-q", repo_url, "-O", "/tmp/packages-microsoft-prod.deb"],
            check=False,
        )
        if result.returncode != 0:
            print_warning(
                f"Failed to download Microsoft repo package for {distro} {version}"
            )
            print_detail("Trying Ubuntu 24.04 as fallback...")
            result = run_cmd(
                [
                    "wget",
                    "-q",
                    "https://packages.microsoft.com/config/ubuntu/24.04/packages-microsoft-prod.deb",
                    "-O",
                    "/tmp/packages-microsoft-prod.deb",
                ],
                check=False,
            )
            if result.returncode != 0:
                print_warning("Failed to download Microsoft repository package")
                return

        result = run_cmd(
            ["dpkg", "-i", "/tmp/packages-microsoft-prod.deb"],
            check=False,
        )
        run_cmd(["rm", "-f", "/tmp/packages-microsoft-prod.deb"], check=False)

        if result.returncode != 0:
            print_warning("Failed to add Microsoft repository")
            return

    # Update package lists
    with Spinner("Updating package lists..."):
        run_cmd(["apt-get", "update", "-q"], check=False)

    # Install .NET SDKs
    with Spinner("Installing .NET SDK 8 (LTS)..."):
        result = run_cmd(
            ["apt-get", "install", "-y", "dotnet-sdk-8.0"],
            env={"DEBIAN_FRONTEND": "noninteractive"},
            check=False,
        )
        if result.returncode == 0:
            print_success(".NET SDK 8 installed")
        else:
            print_warning(".NET SDK 8 installation failed")

    with Spinner("Installing .NET SDK 9..."):
        result = run_cmd(
            ["apt-get", "install", "-y", "dotnet-sdk-9.0"],
            env={"DEBIAN_FRONTEND": "noninteractive"},
            check=False,
        )
        if result.returncode == 0:
            print_success(".NET SDK 9 installed")
        else:
            print_warning(".NET SDK 9 installation failed")


def install_dotnet_sdk_fedora() -> None:
    """Install .NET SDK on Fedora from repos."""
    if cmd_exists("dotnet"):
        print_info(".NET SDK already installed")
        return

    # Fedora has .NET in its repos
    with Spinner("Installing .NET SDK..."):
        result = run_cmd(
            ["dnf", "install", "-y", "dotnet-sdk-8.0", "dotnet-sdk-9.0"],
            check=False,
        )
        if result.returncode == 0:
            print_success(".NET SDK installed")
        else:
            print_warning(".NET SDK installation failed")
