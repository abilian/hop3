# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0


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
    DEFAULT_EXEC,
    Exec,
    InvalidBinaryError,
)

HOP3_USER: Final[str] = "hop3"

# Test override; when None, app_root() derives it from the hop3 user's home.
APP_ROOT: Path | None = None

# Operator allow-list for bind sources: one absolute path prefix per line
# (blank / '#' lines ignored). Absent or empty → default-deny (every bind is
# refused). rootd keeps its own copy (defense in depth); the installer syncs it
# with the server-side HOP3_BIND_VOLUME_ALLOWLIST.
BIND_ALLOWLIST_PATH: Path = Path("/var/lib/hop3-rootd/bind-allowlist")

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


# --- Bind allow-list ------------------------------------------------------


def bind_allowlist() -> list[Path]:
    """Operator-allowed bind source prefixes, realpath-resolved. [] = deny all."""
    if not BIND_ALLOWLIST_PATH.exists():
        return []
    try:
        text = BIND_ALLOWLIST_PATH.read_text(encoding="utf-8")
    except OSError as e:
        raise MountError(
            f"could not read bind allow-list {BIND_ALLOWLIST_PATH}: {e}"
        ) from e
    prefixes: list[Path] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        prefixes.append(Path(os.path.realpath(line)))
    return prefixes


def _is_under(path: Path, prefixes: list[Path]) -> bool:
    """True if ``path`` is one of, or below, an allow-list prefix."""
    p = str(path)
    for prefix in prefixes:
        pref = str(prefix)
        if p == pref or p.startswith(pref + os.sep):
            return True
    return False


# --- Binary resolution ----------------------------------------------------


def _mount_bin(exec: Exec = DEFAULT_EXEC) -> str:
    binary = exec.resolve("mount")
    if binary is None:
        raise MountUnavailableError(
            "the 'mount' binary is not available/allow-listed on this host"
        )
    return binary


def _umount_bin(exec: Exec = DEFAULT_EXEC) -> str:
    binary = exec.resolve("umount")
    if binary is None:
        raise MountUnavailableError(
            "the 'umount' binary is not available/allow-listed on this host"
        )
    return binary


# --- Mount-state query ----------------------------------------------------


def is_mounted(mountpoint: Path) -> bool:
    """True if ``mountpoint`` is an active mount per /proc/self/mountinfo.

    Returns False when mountinfo is absent (non-Linux dev hosts) — the real
    teardown verification runs on Linux where it exists. A mountinfo that
    *exists* but can't be read is a kernel-health fault, not "not mounted":
    raising stops reconcile from silently dropping a live mount's state row
    on a transient read error.
    """
    if not _MOUNTINFO.exists():
        return False
    try:
        text = _MOUNTINFO.read_text(encoding="utf-8")
    except OSError as e:
        raise MountError(f"could not read {_MOUNTINFO}: {e}") from e
    for line in text.splitlines():
        # mountinfo: "<id> <pid> <maj:min> <root> <mount-point> <opts> ..."
        parts = line.split()
        if len(parts) >= 5 and parts[4] == str(mountpoint):
            return True
    return False


# --- Public operations (called by ops/mount.py) ---------------------------


def mount_tmpfs(
    app_name: str,
    target: str,
    size_bytes: int,
    mode: str | None = None,
    *,
    exec: Exec = DEFAULT_EXEC,
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

    result = exec.run(
        [_mount_bin(exec), "-t", "tmpfs", "-o", opts, "tmpfs", str(mp)],
        timeout=_MOUNT_TIMEOUT_SECONDS,
    )
    if not result.success:
        raise MountError(f"mounting tmpfs at {mp} failed: {result.stderr.strip()}")
    return {"mountpoint": str(mp), "type": "tmpfs"}


def mount_bind(
    app_name: str,
    target: str,
    source: str,
    *,
    read_only: bool = False,
    exec: Exec = DEFAULT_EXEC,
) -> dict[str, Any]:
    """Bind-mount an operator-allowed host ``source`` at the app's ``target``.

    Default-deny: the realpath-resolved source must be under an allow-list
    prefix (rootd's own copy — defense in depth) and must already exist (we
    never auto-create operator space). ``read_only`` is enforced with a
    follow-up remount; if that fails the bind is torn down and the deploy
    fails loud rather than serving a writable mount that asked to be ro.
    """
    real_source = Path(os.path.realpath(source))
    allow = bind_allowlist()
    if not _is_under(real_source, allow):
        allowed = ", ".join(str(p) for p in allow) or "(none configured)"
        raise MountError(
            f"bind source {source!r} is not under any operator-allowed path "
            f"({allowed}); add it to the rootd bind allow-list or use a persist volume"
        )
    if not real_source.exists():
        raise MountError(
            f"bind source {real_source} does not exist; it must be created by the "
            "operator before an app can bind it"
        )

    mp = mountpoint_for(app_name, target)
    try:
        mp.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise MountError(f"could not create mountpoint {mp}: {e}") from e

    result = exec.run(
        [_mount_bin(exec), "--bind", str(real_source), str(mp)],
        timeout=_MOUNT_TIMEOUT_SECONDS,
    )
    if not result.success:
        raise MountError(
            f"bind-mounting {real_source} at {mp} failed: {result.stderr.strip()}"
        )

    if read_only:
        ro = exec.run(
            [_mount_bin(exec), "-o", "remount,bind,ro", str(mp)],
            timeout=_MOUNT_TIMEOUT_SECONDS,
        )
        if not ro.success:
            # Couldn't honor read_only — undo the bind, don't leave it writable.
            exec.run([_umount_bin(exec), str(mp)], timeout=_MOUNT_TIMEOUT_SECONDS)
            raise MountError(
                f"could not remount bind {mp} read-only: {ro.stderr.strip()}"
            )

    return {
        "mountpoint": str(mp),
        "type": "bind",
        "source": str(real_source),
        "read_only": read_only,
    }


def _umount(mp: Path, *, exec: Exec = DEFAULT_EXEC) -> str:
    """umount ``mp``, lazy-detaching a busy mount. Returns the method used.

    Raises MountError if both the plain and lazy umount fail — teardown must
    not silently leave a mount behind.
    """
    try:
        result = exec.run([_umount_bin(exec), str(mp)], timeout=_MOUNT_TIMEOUT_SECONDS)
    except InvalidBinaryError as e:
        raise MountUnavailableError(str(e)) from e
    if result.success:
        return "umount"

    # Busy (a process with cwd inside) → lazy detach as a fallback.
    lazy = exec.run([_umount_bin(exec), "-l", str(mp)], timeout=_MOUNT_TIMEOUT_SECONDS)
    if lazy.success:
        return "umount -l"

    raise MountError(
        f"could not unmount {mp}: {result.stderr.strip()} "
        f"(lazy detach also failed: {lazy.stderr.strip()})"
    )


def unmount(app_name: str, target: str, *, exec: Exec = DEFAULT_EXEC) -> dict[str, Any]:
    """Unmount the app's ``target``. Idempotent; lazy-detaches a busy mount.

    Returns ``{unmounted, mountpoint, method|kernel_state}``.
    """
    mp = mountpoint_for(app_name, target)
    if not is_mounted(mp):
        return {"unmounted": False, "mountpoint": str(mp), "kernel_state": "absent"}
    method = _umount(mp, exec=exec)
    return {"unmounted": True, "mountpoint": str(mp), "method": method}


def unmount_path(mountpoint: Path, *, exec: Exec = DEFAULT_EXEC) -> str:
    """Unmount a specific path (reconcile orphan cleanup). Returns the method."""
    return _umount(mountpoint, exec=exec)


def list_mounts_under_app_root() -> list[str]:
    """Active mountpoints under the app root, per /proc/self/mountinfo.

    Only rootd mounts under ``<app_root>/*/src`` (apps run unprivileged and
    can't mount), so any such mount with no state row is a rootd orphan. []
    when mountinfo is absent (non-Linux dev hosts); a present-but-unreadable
    mountinfo raises MountError so the orphan scan degrades loud, not silent.
    """
    if not _MOUNTINFO.exists():
        return []
    prefix = str(app_root()) + os.sep
    try:
        text = _MOUNTINFO.read_text(encoding="utf-8")
    except OSError as e:
        raise MountError(f"could not read {_MOUNTINFO}: {e}") from e
    out: list[str] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[4].startswith(prefix):
            out.append(parts[4])
    return out
