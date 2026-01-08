# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Common dependency installation utilities shared across distros."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from hop3_installer.common import (
    Spinner,
    cmd_exists,
    print_detail,
    print_info,
    print_success,
    print_warning,
    run_cmd,
)

from .config import HOME_DIR
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


def install_dotnet_sdk_debian() -> None:
    """Install .NET SDK on Debian/Ubuntu from Microsoft repository."""
    if cmd_exists("dotnet"):
        print_info(".NET SDK already installed")
        return

    # Add Microsoft package repository for Debian/Ubuntu
    with Spinner("Adding Microsoft package repository..."):
        # Download and install the Microsoft package signing key
        run_cmd(
            [
                "wget",
                "-q",
                "https://packages.microsoft.com/config/ubuntu/24.04/packages-microsoft-prod.deb",
                "-O",
                "/tmp/packages-microsoft-prod.deb",
            ],
            check=False,
        )
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
