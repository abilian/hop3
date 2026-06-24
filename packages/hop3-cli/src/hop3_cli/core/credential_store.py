# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Per-server token store (ADR 042, 2nd revision).

Bearer tokens live in ``~/.config/hop3-cli/credentials.toml``, keyed by the
*canonical* server address. This is invisible plumbing: ``hop3 login`` / ``hop3
init`` populate it, deploy/RPC read it, and the user never edits it by hand.

Because the file aggregates every server's token, it is created ``0o600`` (parent
dir ``0o700``) and we **abort loud** rather than ever leave it group/world
readable — no best-effort-and-suppress (Hop3's "errors are never silent" rule).

Shape::

    [servers."ssh://root@prod.example.com:22"]
    token = "eyJ..."
"""

from __future__ import annotations

import contextlib
import os
import stat
import tempfile
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import toml
import tomllib

from hop3_cli.core.paths import config_dir

if TYPE_CHECKING:
    from pathlib import Path

CREDENTIALS_FILENAME = "credentials.toml"

# Default ports made explicit so one instance reached two ways doesn't split.
_DEFAULT_PORTS = {"ssh": 22, "http": 80, "https": 443}


class CredentialStoreError(RuntimeError):
    """Raised when the token store can't be read, written, or secured."""


def canonicalize(address: str) -> str:
    """Normalise a server address to a stable token-store key.

    ``scheme://[user@]host[:port]`` → lowercased scheme/host, default port made
    explicit, the **user preserved** (never dropped — different users are
    different identities, and conflating them could serve one principal's token
    to another). A string we can't parse as a URL is returned stripped, as-is.
    """
    raw = address.strip()
    parts = urlsplit(raw)
    if not parts.scheme or not parts.hostname:
        return raw
    scheme = parts.scheme.lower()
    host = parts.hostname.lower()
    user = parts.username
    try:
        port = parts.port or _DEFAULT_PORTS.get(scheme)
    except ValueError:
        port = _DEFAULT_PORTS.get(scheme)
    userinfo = f"{user}@" if user else ""
    portinfo = f":{port}" if port else ""
    return f"{scheme}://{userinfo}{host}{portinfo}"


def get_token(address: str) -> str | None:
    """Return the stored token for ``address`` (any equivalent form), or None."""
    entry = _read().get(canonicalize(address))
    if isinstance(entry, dict):
        token = entry.get("token")
        if isinstance(token, str) and token:
            return token
    return None


def set_token(address: str, token: str) -> None:
    """Store ``token`` for ``address`` (keyed by its canonical form)."""
    servers = _read()
    servers[canonicalize(address)] = {"token": token}
    _write(servers)


def remove_token(address: str) -> bool:
    """Drop the token for ``address``. Returns True if one was present."""
    servers = _read()
    if servers.pop(canonicalize(address), None) is not None:
        _write(servers)
        return True
    return False


def known_servers() -> list[str]:
    """Canonical addresses of every server with a stored token (the known set)."""
    return sorted(_read())


# --------------------------------------------------------------------------
# Storage internals — fail-loud permissions
# --------------------------------------------------------------------------


def _credentials_path() -> Path:
    return config_dir() / CREDENTIALS_FILENAME


def _read() -> dict[str, dict[str, Any]]:
    path = _credentials_path()
    if not path.is_file():
        return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        msg = f"cannot read token store {path}: {exc}"
        raise CredentialStoreError(msg) from exc
    servers = data.get("servers", {})
    return servers if isinstance(servers, dict) else {}


def _write(servers: dict[str, dict[str, Any]]) -> None:
    path = _credentials_path()
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    # Tighten the parent dir to 0o700; abort loud if we can't (it holds tokens).
    try:
        os.chmod(parent, 0o700)
    except OSError as exc:
        msg = f"cannot secure {parent} to 0o700: {exc}"
        raise CredentialStoreError(msg) from exc

    # mkstemp creates the temp file 0o600 (umask-independent); os.replace keeps it.
    fd, tmp = tempfile.mkstemp(prefix=".credentials.", suffix=".tmp", dir=str(parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            toml.dump({"servers": servers}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise

    # Verify the result is private; refuse loudly to leave tokens readable.
    mode = stat.S_IMODE(os.stat(path).st_mode)
    if mode & 0o077:
        msg = (
            f"{path} is group/world-accessible (mode {oct(mode)}); refusing to "
            "leave bearer tokens readable. Fix the file's permissions and retry."
        )
        raise CredentialStoreError(msg)
