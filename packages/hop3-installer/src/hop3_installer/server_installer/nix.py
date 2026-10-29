# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Nix package manager installation.

Installs Nix using the official installer. Supports two modes:
- Multi-user (daemon) mode: When systemd is available, provides better isolation
- Single-user mode: Fallback for containers/non-systemd environments

Both modes allow the hop3 user to run nix-build for deploying Nix-based apps.
"""

from __future__ import annotations

import contextlib
import os
import shlex
import ssl
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from hop3_installer.common import (
    CommandError,
    Runner,
    Spinner,
    cmd_exists,
    control_service,
    has_systemd,
    print_detail,
    print_info,
    print_success,
    run_cmd,
)
from hop3_installer.constants import HOME_DIR, HOP3_USER

from .user import run_as_hop3, run_as_hop3_shell

# Nix official installer URL
NIX_INSTALLER_URL = "https://nixos.org/nix/install"

# Profile script paths for different installation modes
NIX_DAEMON_PROFILE = Path("/nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh")
NIX_SINGLE_USER_PROFILE = HOME_DIR / ".nix-profile/etc/profile.d/nix.sh"


def install_nix() -> None:
    """
    Install Nix package manager.

    Uses multi-user (daemon) mode when systemd is available,
    falls back to single-user mode for containers/non-systemd environments.

    Called when the operator asked for ``--with nix``, so a Nix that did not
    install is a failed install: raise ``CommandError`` rather than warn. A
    warning let the install report success while every Nix app on the box then
    failed to build, and the e2e suite skipped its Nix fixtures for months.
    """
    print_info("Installing Nix package manager...")

    use_daemon_mode = has_systemd()
    if _is_nix_installed():
        print_success("Nix already installed")
    else:
        _run_official_installer(daemon_mode=use_daemon_mode)

    # On every install, not only the first: see _configure_hop3_nix_access.
    _configure_hop3_nix_access(daemon_mode=use_daemon_mode)

    if not _verify_nix_installation():
        _fail("Nix is installed but the hop3 user cannot run `nix --version`")
    mode_str = "multi-user" if use_daemon_mode else "single-user"
    print_success(f"Nix package manager ready ({mode_str} mode)")


def _run_official_installer(*, daemon_mode: bool) -> None:
    """Download and run the official Nix installer; raise if either fails."""
    if not cmd_exists("xz"):
        _fail(
            "the Nix installer needs `xz`; the Nix prerequisite packages were "
            "not installed"
        )

    if daemon_mode:
        print_detail("Using multi-user (daemon) mode")
    else:
        print_detail("Using single-user mode (no systemd)")

    # Download the official installer
    installer_path = _download_nix_installer()
    if not installer_path:
        _fail(f"could not download the Nix installer from {NIX_INSTALLER_URL}")

    # Run installer
    if not _run_nix_installer(installer_path, daemon_mode=daemon_mode):
        _fail("the Nix installer exited with an error (its output is above)")


@dataclass
class NixInstallError(CommandError):
    """A ``--with nix`` install that did not end with a working Nix."""

    def __str__(self) -> str:
        return self.stderr


def _fail(reason: str) -> NoReturn:
    raise NixInstallError(
        cmd=["hop3-install", "--with", "nix"], returncode=1, stderr=reason
    )


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


def _download_nix_installer() -> Path | None:
    """
    Download the official Nix installer script.

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
    """
    Create /nix directory with correct ownership for single-user mode.

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
    """
    Run the Nix installer.

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
                ["sh", str(installer_path), "--no-daemon", "--yes"],
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


#: Settings Hop3 requires in nix.conf, rewritten on every install:
#:  * sandbox = relaxed: allow __noChroot builds (apps that run
#:    npm/pip/composer install during the build phase). The nix 2.x default,
#:    `sandbox = true`, rejects those derivations outright.
#:  * min-free = 0: pin auto-GC OFF. A disk-pressure garbage collect must
#:    never reclaim a *running* app's nix closure mid-deploy: forgejo's
#:    wrapper execs a hardcoded ${forgejo}/bin path, and a GC firing during a
#:    rebuild would delete it, killing the daemon with "No such file or
#:    directory". The builder holds per-app GC roots; this removes the trigger.
NIX_SETTINGS = {"sandbox": "relaxed", "min-free": "0"}
NIX_CONF_HEADER = "# Hop3 nix settings (see server_installer/nix.py)"
ETC_NIX_CONF = Path("/etc/nix/nix.conf")


def reconciled_nix_conf(existing: str) -> str:
    """
    ``existing`` with Hop3's settings block at the end, and no other line
    setting one of its keys (nix lets the last assignment win, but a reader
    should not have to know that).
    """
    kept = [
        line
        for line in existing.splitlines()
        if line.strip() != NIX_CONF_HEADER
        and line.split("=", 1)[0].strip() not in NIX_SETTINGS
    ]
    while kept and not kept[-1].strip():
        kept.pop()
    block = [NIX_CONF_HEADER, *(f"{k} = {v}" for k, v in NIX_SETTINGS.items())]
    return "\n".join([*kept, "", *block] if kept else block) + "\n"


def _configure_hop3_nix_access(
    *,
    daemon_mode: bool,
    home: Path = HOME_DIR,
    etc_conf: Path = ETC_NIX_CONF,
    run: Runner = run_cmd,
    as_hop3_shell: Runner = run_as_hop3_shell,
    systemd: bool | None = None,
) -> None:
    """
    Point the hop3 user at Nix and bring nix.conf to Hop3's settings.

    Every step runs on every install, so a redeploy reconciles what a fresh
    install writes: the ``.bashrc`` profile line, nix.conf, and a daemon
    restart so the daemon reads it. An early return on "already in .bashrc"
    used to skip the rest, and a server kept whatever nix.conf it first got.

    Daemon mode reads /etc/nix/nix.conf; single-user mode reads
    ~/.config/nix/nix.conf for the user that runs nix-build (hop3).

    Everything under hop3's home is read and written *as hop3*: an app runs
    as hop3 and can plant a symlink there (``~/.config/nix/nix.conf`` ->
    ``/etc/passwd``), which root would follow on the next redeploy.
    """
    profile_script = NIX_DAEMON_PROFILE if daemon_mode else NIX_SINGLE_USER_PROFILE
    _ensure_bashrc_sources(home / ".bashrc", profile_script, as_hop3_shell)

    if systemd is None:
        systemd = has_systemd()
    if daemon_mode:

        def write_etc(content: str) -> None:
            etc_conf.parent.mkdir(parents=True, exist_ok=True)
            etc_conf.write_text(content)

        etc_existing = etc_conf.read_text() if etc_conf.exists() else ""
        _reconcile_nix_conf(etc_conf, etc_existing, write_etc)
        # The daemon reads nix.conf at start: a failed restart leaves the
        # sandbox setting unapplied and every __noChroot build failing later.
        control_service("enable", "nix-daemon", run=run, systemd=systemd)
        control_service("restart", "nix-daemon", run=run, systemd=systemd)
    else:
        user_conf = home / ".config" / "nix" / "nix.conf"

        def write_user(content: str) -> None:
            as_hop3_shell(
                f"mkdir -p -- {shlex.quote(str(user_conf.parent))}", check=True
            )
            _write_as_hop3(user_conf, content, as_hop3_shell)

        user_existing = _read_as_hop3(user_conf, as_hop3_shell)
        _reconcile_nix_conf(user_conf, user_existing, write_user)

    # Belt-and-suspenders with min-free=0: also stop any periodic GC timer a
    # host/channel image may ship, so a scheduled `nix-collect-garbage` can't
    # reclaim a running app's closure between deploys. Absent on most hosts,
    # hence check=False; without systemd there is no timer to stop.
    if systemd:
        run(["systemctl", "disable", "--now", "nix-gc.timer"], check=False)

    # No nixpkgs channel is configured. Every Hop3 build expression pins its own
    # nixpkgs via `import (fetchTarball { url; sha256; })` at a specific nixos-24.11
    # commit (see the nix-gen templates' base.py and the hand-crafted hop3.nix
    # files), so `<nixpkgs>` / NIX_PATH is never consulted and there is no channel
    # to keep updated. The pinned commit's binaries are in cache.nixos.org, so the
    # cache-miss / slow-build risk the channel used to guard against is gone.


def _ensure_bashrc_sources(bashrc: Path, profile_script: Path, shell: Runner) -> None:
    """Append the line sourcing ``profile_script`` to hop3's ``bashrc`` if absent."""
    existing = _read_as_hop3(bashrc, shell)
    if str(profile_script) in existing:
        return
    print_detail(f"Adding Nix profile ({profile_script}) to {bashrc}")
    source_line = f'[ -e "{profile_script}" ] && . "{profile_script}"'
    _write_as_hop3(bashrc, f"{existing}\n# Nix package manager\n{source_line}\n", shell)


#: Exit status of `_read_as_hop3`'s script when the file does not exist.
_ABSENT = 3


def _read_as_hop3(path: Path, shell: Runner) -> str:
    """The text of a file under hop3's home, read as hop3; ``""`` if absent."""
    quoted = shlex.quote(str(path))
    result = shell(f"test -e {quoted} || exit {_ABSENT}; cat -- {quoted}")
    if result.returncode == _ABSENT:
        return ""
    if result.returncode != 0:
        _fail(f"cannot read {path} as {HOP3_USER}: {result.stderr.strip()}")
    return result.stdout


def _write_as_hop3(path: Path, content: str, shell: Runner) -> None:
    """Replace a file under hop3's home with ``content``, written as hop3."""
    shell(f"cat > {shlex.quote(str(path))}", check=True, stdin_text=content)


def _reconcile_nix_conf(
    path: Path, existing: str, write: Callable[[str], None]
) -> None:
    """Bring the nix.conf at ``path`` to Hop3's settings, writing only a change."""
    wanted = reconciled_nix_conf(existing)
    if wanted == existing:
        print_detail(f"Nix settings up to date in {path}")
        return
    write(wanted)
    print_detail(f"Wrote nix settings to {path}")


def _verify_nix_installation() -> bool:
    """
    Verify Nix installation works for hop3 user.

    Returns:
        True if verification passed.
    """
    # The daemon is enabled and restarted by _configure_hop3_nix_access; this
    # only checks the result.
    # Try to find and source the profile script
    # Check both possible locations
    for profile_script in [NIX_DAEMON_PROFILE, NIX_SINGLE_USER_PROFILE]:
        check_cmd = f". {shlex.quote(str(profile_script))} 2>/dev/null && nix --version"
        result = run_as_hop3_shell(check_cmd)

        if result.returncode == 0:
            version = result.stdout.strip()
            print_detail(f"Nix version: {version}")
            return True

    # Try without sourcing (maybe it's already in PATH)
    result = run_as_hop3(["nix", "--version"])
    if result.returncode == 0:
        version = result.stdout.strip()
        print_detail(f"Nix version: {version}")
        return True

    print_detail("nix command not working for hop3 user")
    return False
