# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Nix package manager installation.

Installs Nix using the official installer. Supports two modes:
- Multi-user (daemon) mode: When systemd is available, provides better isolation
- Single-user mode: Fallback for containers/non-systemd environments

Both modes allow the hop3 user to run nix-build for deploying Nix-based apps.
"""

from __future__ import annotations

import contextlib
import os
import ssl
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from hop3_installer.common import (
    Spinner,
    cmd_exists,
    has_systemd,
    print_detail,
    print_info,
    print_success,
    print_warning,
    run_cmd,
)
from hop3_installer.constants import HOME_DIR

from .user import run_as_hop3

# Nix official installer URL
NIX_INSTALLER_URL = "https://nixos.org/nix/install"

# Profile script paths for different installation modes
NIX_DAEMON_PROFILE = Path("/nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh")
NIX_SINGLE_USER_PROFILE = HOME_DIR / ".nix-profile/etc/profile.d/nix.sh"


def install_nix() -> None:
    """Install Nix package manager.

    Uses multi-user (daemon) mode when systemd is available,
    falls back to single-user mode for containers/non-systemd environments.

    This is the main entry point called from deps_common.py.
    Nix installation is non-critical - failures warn but don't abort.
    """
    print_info("Installing Nix package manager...")

    # Check if Nix is already installed
    if _is_nix_installed():
        print_success("Nix already installed")
        _verify_nix_installation()
        return

    # Determine installation mode
    use_daemon_mode = _has_systemd()
    if use_daemon_mode:
        print_detail("Using multi-user (daemon) mode")
    else:
        print_detail("Using single-user mode (no systemd)")

    # Download the official installer
    installer_path = _download_nix_installer()
    if not installer_path:
        print_warning("Failed to download Nix installer")
        return

    # Run installer
    if not _run_nix_installer(installer_path, daemon_mode=use_daemon_mode):
        print_warning("Nix installation failed")
        return

    # Configure hop3 user access
    _configure_hop3_nix_access(daemon_mode=use_daemon_mode)

    # Verify installation
    if _verify_nix_installation():
        mode_str = "multi-user" if use_daemon_mode else "single-user"
        print_success(f"Nix package manager installed ({mode_str} mode)")
    else:
        print_warning("Nix installed but verification failed")


def _is_nix_installed() -> bool:
    """Check if Nix is already installed."""
    # Check for nix binary in PATH
    if cmd_exists("nix"):
        return True

    # Check for nix store (daemon mode installation)
    if Path("/nix/store").exists():
        return True

    # Check for single-user installation
    return NIX_SINGLE_USER_PROFILE.exists()


# _has_systemd lives in common.has_systemd — kept here as a thin alias
# so existing call sites in this module read clearly.
_has_systemd = has_systemd


def _download_nix_installer() -> Path | None:
    """Download the official Nix installer script.

    Uses urllib (stdlib only) to download the installer.

    Returns:
        Path to downloaded installer, or None on failure.
    """
    with Spinner("Downloading Nix installer..."):
        try:
            # Create SSL context for HTTPS
            ssl_context = ssl.create_default_context()

            # Download to a temporary file
            with urllib.request.urlopen(
                NIX_INSTALLER_URL,
                context=ssl_context,
                timeout=60,
            ) as response:
                installer_content = response.read()

            # Write to temporary file
            fd, path = tempfile.mkstemp(suffix=".sh", prefix="nix-install-")
            os.write(fd, installer_content)
            os.close(fd)

            installer_path = Path(path)
            installer_path.chmod(0o755)

            print_detail(f"Downloaded installer to {installer_path}")
            return installer_path

        except urllib.error.URLError as e:
            print_detail(f"Download error: {e}")
            return None
        except OSError as e:
            print_detail(f"File error: {e}")
            return None


def _prepare_nix_directory() -> bool:
    """Create /nix directory with correct ownership for single-user mode.

    The Nix installer needs /nix to exist and be owned by the installing user.
    We create this as root before running the installer as hop3.

    Returns:
        True if directory is ready.
    """
    nix_dir = Path("/nix")
    if nix_dir.exists():
        return True

    # Create /nix directory owned by hop3
    result = run_cmd(["mkdir", "-m", "0755", "/nix"], check=False)
    if result.returncode != 0:
        print_detail(f"Failed to create /nix: {result.stderr}")
        return False

    result = run_cmd(["chown", "hop3:hop3", "/nix"], check=False)
    if result.returncode != 0:
        print_detail(f"Failed to chown /nix: {result.stderr}")
        return False

    print_detail("Created /nix directory for hop3 user")
    return True


def _run_nix_installer(installer_path: Path, *, daemon_mode: bool) -> bool:
    """Run the Nix installer.

    Args:
        installer_path: Path to the downloaded installer script.
        daemon_mode: If True, use multi-user daemon mode; otherwise single-user.

    Returns:
        True if installation succeeded.
    """
    mode_desc = "multi-user" if daemon_mode else "single-user"

    # For single-user mode, prepare /nix directory first
    if not daemon_mode:
        if not _prepare_nix_directory():
            print_detail("Failed to prepare /nix directory")
            return False

    with Spinner(f"Running Nix installer ({mode_desc} mode)..."):
        if daemon_mode:
            # Multi-user installation (requires root, uses systemd)
            result = run_cmd(
                ["sh", str(installer_path), "--daemon", "--yes"],
                check=False,
                timeout=600,  # 10 minute timeout
            )
        else:
            # Single-user installation (runs as hop3 user)
            # The installer needs to run as the hop3 user for single-user mode
            result = run_as_hop3(
                f"sh {installer_path} --no-daemon --yes",
                timeout=600,
            )

    # Clean up installer
    with contextlib.suppress(OSError):
        installer_path.unlink()

    if result.returncode != 0:
        print_detail("Installer output:")
        if result.stderr:
            for line in result.stderr.strip().split("\n")[-10:]:
                print_detail(f"  {line}")
        if result.stdout:
            for line in result.stdout.strip().split("\n")[-5:]:
                print_detail(f"  {line}")
        return False

    return True


def _write_nix_conf_setting(path: Path, *, as_hop3: bool) -> None:
    """Write ``sandbox = relaxed`` to a nix.conf, creating it if needed.

    Args:
        path: Target nix.conf path.
        as_hop3: If True, the parent dir and file are created/owned
            by the hop3 user (single-user install). Otherwise as root.
    """
    line = "sandbox = relaxed"
    header = "# Allow __noChroot builds for apps needing network"

    if as_hop3:
        # Single-user: ~/.config/nix/nix.conf must be created by hop3
        # so it can read it later. Avoid quoting hell by writing the
        # file as root and then chown'ing to hop3 — the file lives
        # under the hop3 home so this is safe.
        run_as_hop3(f"mkdir -p {path.parent}")
        existing = run_as_hop3(f"cat {path} 2>/dev/null || true").stdout or ""
        if line in existing:
            print_detail(f"Nix sandbox already relaxed in {path}")
            return
        with path.open("a") as f:
            f.write(f"\n{header}\n{line}\n")
        run_cmd(["chown", "hop3:hop3", str(path)], check=False)
        print_detail(f"Wrote {line} to {path}")
        return

    # Daemon mode: write as root.
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text() if path.exists() else ""
    if line in existing:
        print_detail(f"Nix sandbox already relaxed in {path}")
        return
    with path.open("a") as f:
        f.write(f"\n{header}\n{line}\n")
    print_detail(f"Wrote {line} to {path}")


def _configure_hop3_nix_access(*, daemon_mode: bool) -> None:
    """Configure hop3 user to use Nix.

    Adds the appropriate profile script to hop3's .bashrc.

    Args:
        daemon_mode: Whether daemon mode was used for installation.
    """
    bashrc_path = HOME_DIR / ".bashrc"

    # Choose the appropriate profile script
    if daemon_mode:
        profile_script = NIX_DAEMON_PROFILE
    else:
        profile_script = NIX_SINGLE_USER_PROFILE

    # Source line to add to .bashrc
    source_line = f'[ -e "{profile_script}" ] && . "{profile_script}"'

    # Check if already configured
    if bashrc_path.exists():
        content = bashrc_path.read_text()
        if str(profile_script) in content:
            print_detail("Nix already configured in hop3 .bashrc")
            return

    # Append source line to .bashrc
    print_detail(f"Adding Nix profile ({profile_script}) to hop3 .bashrc")
    with bashrc_path.open("a") as f:
        f.write(f"\n# Nix package manager\n{source_line}\n")

    # Configure Nix to allow __noChroot builds (needed for apps that
    # run npm/pip/composer install during the build phase).
    #
    # Daemon mode reads /etc/nix/nix.conf; single-user mode reads
    # ~/.config/nix/nix.conf for the user that runs nix-build (hop3).
    # Both need `sandbox = relaxed` (or `false`) for __noChroot to
    # take effect — the default in nix 2.x is `sandbox = true`, which
    # rejects __noChroot derivations outright.
    if daemon_mode:
        _write_nix_conf_setting(Path("/etc/nix/nix.conf"), as_hop3=False)
        with contextlib.suppress(Exception):
            run_cmd(["systemctl", "restart", "nix-daemon"])
    else:
        _write_nix_conf_setting(HOME_DIR / ".config" / "nix" / "nix.conf", as_hop3=True)

    # Pin the nixpkgs channel to nixos-24.11 (stable, packages are cached)
    # Without this, Nix may use a rolling channel where packages like
    # nodejs aren't in the binary cache yet, causing hours-long builds.
    for profile in [NIX_DAEMON_PROFILE, NIX_SINGLE_USER_PROFILE]:
        if profile.exists():
            print_detail("Setting nixpkgs channel to nixos-24.11 (stable)")
            run_as_hop3(
                f'. "{profile}" && '
                "nix-channel --add https://nixos.org/channels/nixos-24.11 nixpkgs"
                " && nix-channel --update"
            )
            break


def _verify_nix_installation() -> bool:
    """Verify Nix installation works for hop3 user.

    Returns:
        True if verification passed.
    """
    # For daemon mode, try to start the service
    if _has_systemd():
        run_cmd(["systemctl", "enable", "nix-daemon"], check=False)
        run_cmd(["systemctl", "start", "nix-daemon"], check=False)

    # Try to find and source the profile script
    # Check both possible locations
    for profile_script in [NIX_DAEMON_PROFILE, NIX_SINGLE_USER_PROFILE]:
        check_cmd = f'. "{profile_script}" 2>/dev/null && nix --version'
        result = run_as_hop3(check_cmd)

        if result.returncode == 0:
            version = result.stdout.strip()
            print_detail(f"Nix version: {version}")
            return True

    # Try without sourcing (maybe it's already in PATH)
    result = run_as_hop3("nix --version")
    if result.returncode == 0:
        version = result.stdout.strip()
        print_detail(f"Nix version: {version}")
        return True

    print_detail("nix command not working for hop3 user")
    return False
