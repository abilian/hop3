# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0


"""TCP-forwarder units for addon exposure (`hop3 addon expose`).

A database addon listens only on ``127.0.0.1``; exposing it on a public host
port needs a real forwarder. rootd realises this as a per-addon
``systemd-socket-proxyd`` unit pair:

    hop3-expose-<type>-<name>.socket   ListenStream=0.0.0.0:<public_port>
    hop3-expose-<type>-<name>.service  ExecStart=… 127.0.0.1:<target_port>

rootd never ``exec``s the proxy binary itself — it writes the unit files
(atomic write→fsync→rename, like state.json) and drives the *units* via the
already-allow-listed ``systemctl`` (``ops/nginx.py`` does the same for reload).

**Containment (ADR 041):** the proxy destination host is hardcoded to
``127.0.0.1`` — this primitive can only forward a public port to a *loopback*
port, never to an arbitrary internal host. No secret ever touches a unit file.

``UNIT_DIR`` and ``SOCKET_PROXYD_PATH`` are module attributes so tests can point
them at a tmp dir / fake binary; production uses the systemd defaults.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Final

from hop3_rootd.exec import (
    DEFAULT_EXEC,
    Exec,
    InvalidBinaryError,
)

# systemd system-unit directory (test override via this attribute).
UNIT_DIR: Path = Path("/etc/systemd/system")

# Where systemd ships the socket-proxy helper. First existing candidate wins;
# tests set SOCKET_PROXYD_PATH to bypass the filesystem probe.
SOCKET_PROXYD_PATH: str | None = None
_SOCKET_PROXYD_CANDIDATES: Final[tuple[str, ...]] = (
    "/usr/lib/systemd/systemd-socket-proxyd",
    "/lib/systemd/systemd-socket-proxyd",
)

_UNIT_PREFIX: Final[str] = "hop3-expose-"
_PROXY_TARGET_HOST: Final[str] = "127.0.0.1"  # hardcoded: loopback only
_SYSTEMCTL_TIMEOUT_SECONDS: Final[float] = 15.0


class ProxyError(Exception):
    """A proxy-unit operation failed (dispatcher → kernel_error)."""


class ProxyUnavailableError(ProxyError):
    """systemctl or systemd-socket-proxyd isn't available/allow-listed here."""


# --- Naming ---------------------------------------------------------------


def unit_base_name(addon_type: str, addon_name: str) -> str:
    """Compose the base unit name. Inputs are assumed already validated."""
    return f"{_UNIT_PREFIX}{addon_type}-{addon_name}"


def proxyd_path() -> str:
    """Absolute path of ``systemd-socket-proxyd``, or raise if absent."""
    if SOCKET_PROXYD_PATH is not None:
        return SOCKET_PROXYD_PATH
    for candidate in _SOCKET_PROXYD_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    raise ProxyUnavailableError(
        "systemd-socket-proxyd not found "
        f"(looked in {', '.join(_SOCKET_PROXYD_CANDIDATES)}); "
        "addon exposure needs systemd on this host"
    )


# --- Unit-file rendering --------------------------------------------------


def _socket_unit(addon_type: str, addon_name: str, public_port: int) -> str:
    return (
        "[Unit]\n"
        f"Description=Hop3 expose socket for {addon_type}/{addon_name}\n"
        "\n"
        "[Socket]\n"
        f"ListenStream=0.0.0.0:{public_port}\n"
        "\n"
        "[Install]\n"
        "WantedBy=sockets.target\n"
    )


def _service_unit(addon_type: str, addon_name: str, target_port: int, base: str) -> str:
    return (
        "[Unit]\n"
        f"Description=Hop3 expose proxy for {addon_type}/{addon_name}\n"
        f"Requires={base}.socket\n"
        f"After={base}.socket\n"
        "\n"
        "[Service]\n"
        f"ExecStart={proxyd_path()} {_PROXY_TARGET_HOST}:{target_port}\n"
    )


def _write_unit(path: Path, content: str) -> None:
    """Atomic write (tmp→fsync→rename, 0644), mirroring state.save."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)
    os.chmod(path, 0o644)


# --- systemctl driver -----------------------------------------------------


def _systemctl(*args: str, exec: Exec = DEFAULT_EXEC, check: bool = True) -> None:
    """Run ``systemctl <args>``; raise ProxyError on failure when ``check``.

    ``check=False`` is used for best-effort teardown steps (stopping a unit
    that may already be gone), where a non-zero exit is not an error.
    """
    binary = exec.resolve("systemctl")
    if binary is None:
        raise ProxyUnavailableError(
            "systemctl not available/allow-listed; cannot manage proxy units"
        )
    try:
        result = exec.run([binary, *args], timeout=_SYSTEMCTL_TIMEOUT_SECONDS)
    except InvalidBinaryError as e:
        raise ProxyUnavailableError(str(e)) from e
    if check and not result.success:
        raise ProxyError(f"systemctl {' '.join(args)} failed: {result.stderr.strip()}")


# --- Public operations (called by ops/proxy.py) ---------------------------


def add_proxy(
    addon_type: str,
    addon_name: str,
    public_port: int,
    target_port: int,
    *,
    exec: Exec = DEFAULT_EXEC,
) -> dict[str, Any]:
    """Write + enable the socket-proxy unit pair for an exposed addon.

    Idempotent: overwrites any existing unit of the same name and re-enables.
    Returns ``{unit, public_port, target_port}``.
    """
    base = unit_base_name(addon_type, addon_name)
    socket_path = UNIT_DIR / f"{base}.socket"
    service_path = UNIT_DIR / f"{base}.service"

    # Render the .service first — it calls proxyd_path(), which fails loud if
    # systemd-socket-proxyd is missing, *before* we write anything.
    service_content = _service_unit(addon_type, addon_name, target_port, base)
    _write_unit(socket_path, _socket_unit(addon_type, addon_name, public_port))
    _write_unit(service_path, service_content)

    _systemctl("daemon-reload", exec=exec)
    _systemctl("enable", "--now", f"{base}.socket", exec=exec)

    return {"unit": base, "public_port": public_port, "target_port": target_port}


def remove_proxy(base: str, *, exec: Exec = DEFAULT_EXEC) -> dict[str, Any]:
    """Stop, disable and delete a proxy unit pair. Idempotent.

    ``base`` is the bare ``hop3-expose-<type>-<name>`` name (composed by the op
    from validated inputs, or read off disk by reconcile). Returns
    ``{removed, unit}``; ``removed`` is False when nothing was present.
    """
    socket_path = UNIT_DIR / f"{base}.socket"
    service_path = UNIT_DIR / f"{base}.service"
    present = socket_path.exists() or service_path.exists()

    # Best-effort stop/disable (the units may already be inactive/gone).
    _systemctl("disable", "--now", f"{base}.socket", exec=exec, check=False)
    _systemctl("stop", f"{base}.service", exec=exec, check=False)

    for path in (socket_path, service_path):
        try:
            path.unlink(missing_ok=True)
        except OSError as e:
            raise ProxyError(f"could not remove {path}: {e}") from e

    # daemon-reload so systemd forgets the now-deleted units.
    _systemctl("daemon-reload", exec=exec, check=False)

    return {"removed": present, "unit": base}


def list_units() -> list[str]:
    """Base names of every ``hop3-expose-*.socket`` unit on disk (for reconcile).

    Returns [] when the unit dir doesn't exist. Only rootd writes these, so a
    unit with no state row is a rootd orphan from a crashed expose.
    """
    if not UNIT_DIR.exists():
        return []
    suffix = ".socket"
    out: list[str] = []
    for child in UNIT_DIR.iterdir():
        name = child.name
        if name.startswith(_UNIT_PREFIX) and name.endswith(suffix):
            out.append(name[: -len(suffix)])
    return out
