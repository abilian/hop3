# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: TRY003, EM101, EM102

"""Volume mount operations for native ``[[volumes]]`` (ADR 046 §2 / P2.1).

rootd is the only component permitted to call ``mount(8)`` / ``umount(8)``
(ADR 041). This module builds and runs those commands via the exec allow-list;
``ops/mount.py`` orchestrates them and persists state.

Path discipline (ADR 041 §1: the daemon owns the path allow-list): callers pass
``app_name`` + a *relative* ``target``, never an absolute mountpoint. rootd
derives the mountpoint as ``<app_root>/<app>/src/<target>`` and re-checks it
stays under the app's src dir, so a malicious target can't escape the app tree.
``APP_ROOT`` is derived from the hop3 user's home (lazily, so importing this on
a host without a hop3 user — dev/CI — doesn't fail); tests override it.
"""

from __future__ import annotations

import os
import pwd
from pathlib import Path
from typing import Any, Final

from hop3_rootd.exec import (
    InvalidBinaryError,
    resolve_allowed_binary,
    run as exec_run,
)

HOP3_USER: Final[str] = "hop3"

# Test override; when None, app_root() derives it from the hop3 user's home.
APP_ROOT: Path | None = None

_MOUNTINFO: Path = Path("/proc/self/mountinfo")
_MOUNT_TIMEOUT_SECONDS: Final[float] = 15.0


class MountError(Exception):
    """A mount/umount operation failed (dispatcher → kernel_error)."""


class MountUnavailableError(MountError):
    """The mount/umount binary isn't available/allow-listed on this host."""


# --- Path derivation ------------------------------------------------------


def app_root() -> Path:
    """Root of the app tree (``<hop3-home>/apps``). Raises if undeterminable."""
    if APP_ROOT is not None:
        return APP_ROOT
    try:
        home = pwd.getpwnam(HOP3_USER).pw_dir
    except KeyError as e:
        raise MountError(
            f"cannot derive the app root: user {HOP3_USER!r} not found on this host"
        ) from e
    return Path(home) / "apps"


def mountpoint_for(app_name: str, target: str) -> Path:
    """Build + validate the mountpoint for ``target`` under the app's src dir.

    ``app_name``/``target`` are assumed already field-validated; this is the
    defense-in-depth path-escape check (mirrors the persist-volume symlink
    guard) in case validation was bypassed.
    """
    src = app_root() / app_name / "src"
    norm = os.path.normpath(src / target)
    src_str = str(src)
    if norm != src_str and not norm.startswith(src_str + os.sep):
        raise MountError(f"mount target {target!r} escapes the app source tree ({src})")
    return Path(norm)


# --- Binary resolution ----------------------------------------------------


def _mount_bin() -> str:
    binary = resolve_allowed_binary("mount")
    if binary is None:
        raise MountUnavailableError(
            "the 'mount' binary is not available/allow-listed on this host"
        )
    return binary


def _umount_bin() -> str:
    binary = resolve_allowed_binary("umount")
    if binary is None:
        raise MountUnavailableError(
            "the 'umount' binary is not available/allow-listed on this host"
        )
    return binary


# --- Mount-state query ----------------------------------------------------


def is_mounted(mountpoint: Path) -> bool:
    """True if ``mountpoint`` is an active mount per /proc/self/mountinfo.

    Returns False when mountinfo is unavailable (non-Linux dev hosts); the
    real teardown verification runs on Linux where it exists.
    """
    if not _MOUNTINFO.exists():
        return False
    target = str(mountpoint)
    try:
        text = _MOUNTINFO.read_text(encoding="utf-8")
    except OSError:
        return False
    for line in text.splitlines():
        # mountinfo: "<id> <pid> <maj:min> <root> <mount-point> <opts> ..."
        parts = line.split()
        if len(parts) >= 5 and parts[4] == target:
            return True
    return False


# --- Public operations (called by ops/mount.py) ---------------------------


def mount_tmpfs(
    app_name: str, target: str, size_bytes: int, mode: str | None = None
) -> dict[str, Any]:
    """Mount a sized tmpfs at the app's ``target``. Idempotent-ish.

    Creates the mountpoint, then ``mount -t tmpfs -o size=…[,mode=…]``. A tmpfs
    is scratch, so any shipped content at ``target`` is intentionally shadowed.
    """
    mp = mountpoint_for(app_name, target)
    try:
        mp.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise MountError(f"could not create mountpoint {mp}: {e}") from e

    opts = f"size={size_bytes}"
    if mode is not None:
        opts += f",mode={mode}"

    result = exec_run(
        [_mount_bin(), "-t", "tmpfs", "-o", opts, "tmpfs", str(mp)],
        timeout=_MOUNT_TIMEOUT_SECONDS,
    )
    if not result.success:
        raise MountError(f"mounting tmpfs at {mp} failed: {result.stderr.strip()}")
    return {"mountpoint": str(mp), "type": "tmpfs"}


def unmount(app_name: str, target: str) -> dict[str, Any]:
    """Unmount the app's ``target``. Idempotent; lazy-detaches a busy mount.

    Returns ``{unmounted, mountpoint, method|kernel_state}``. A still-busy mount
    after a lazy detach is a hard error (teardown must not silently leave it).
    """
    mp = mountpoint_for(app_name, target)
    if not is_mounted(mp):
        return {"unmounted": False, "mountpoint": str(mp), "kernel_state": "absent"}

    try:
        result = exec_run([_umount_bin(), str(mp)], timeout=_MOUNT_TIMEOUT_SECONDS)
    except InvalidBinaryError as e:
        raise MountUnavailableError(str(e)) from e
    if result.success:
        return {"unmounted": True, "mountpoint": str(mp), "method": "umount"}

    # Busy (a process with cwd inside) → lazy detach as a fallback.
    lazy = exec_run([_umount_bin(), "-l", str(mp)], timeout=_MOUNT_TIMEOUT_SECONDS)
    if lazy.success:
        return {"unmounted": True, "mountpoint": str(mp), "method": "umount -l"}

    raise MountError(
        f"could not unmount {mp}: {result.stderr.strip()} "
        f"(lazy detach also failed: {lazy.stderr.strip()})"
    )
