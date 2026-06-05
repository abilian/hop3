# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Reader and writer for ``~/.config/hop3-cli/servers.toml`` (ADR 042 §File layout).

This file is the new home for **server bindings** — what the CLI used to
call "contexts" pre-ADR-042. Each record is a URL + auth-token + SSH
settings + an optional ``default_app`` (the server-level app-resolution
fallback, source #8 in the chain).

Shape::

    [servers.dev]
    url = "https://hop3-dev.example.com"
    token = "<jwt>"
    ssh_user = "root"
    ssh_port = 22
    protected = false
    default_app = ""

The writer is atomic (mkstemp + ``os.replace`` + parent fsync via the
shared ``atomic_write_toml`` helper) and the file is chmodded to 0o600
because it stores the JWT auth token.

This module deliberately does *not* know about the legacy
``config.toml [contexts.*]`` shape. The legacy reads continue to live
in ``Config`` for one release; ``hop3 server`` writes go through this
module. ``migrate_legacy_records`` is the one-shot move performed by
``hop3 server`` on first use.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomllib

from hop3_cli.core.local_overlay import atomic_write_toml

# Filename relative to the platform-dependent CLI config dir.
SERVERS_TOML_FILENAME = "servers.toml"
LEGACY_CONFIG_FILENAME = "config.toml"
LEGACY_BACKUP_FILENAME = "config.toml.pre-042.bak"


@dataclass(frozen=True)
class ServerRecord:
    """A single server record (server-binding) — typed view of one entry.

    Mirrors the legacy ``Context`` dataclass minus the ``Context``-only
    semantics: this is purely "how do I reach this Hop3 server, and what
    is its default app fallback?".

    Sensitive fields (``token``, ``ssh_key``, ``ssl_cert``) are
    ``repr=False`` so that ``repr(rec)``, debugger pretty-printing,
    exception tracebacks and pytest failure output never leak the
    underlying secret. The class's ``__repr__`` is overridden to emit
    ``token='<set>' / '<unset>'`` sentinels in their place.
    """

    name: str
    url: str
    token: str = field(default="", repr=False)
    ssh_user: str = "root"
    ssh_port: int = 22
    ssh_key: str = field(default="", repr=False)
    ssl_cert: str = field(default="", repr=False)
    verify_ssl: bool = True
    protected: bool = False
    default_app: str = ""

    def __repr__(self) -> str:
        """Token-redacted repr — never leaks the JWT in logs or tracebacks."""

        def sentinel(value: str) -> str:
            return "<set>" if value else "<unset>"

        return (
            f"ServerRecord(name={self.name!r}, url={self.url!r}, "
            f"token={sentinel(self.token)}, "
            f"ssh_user={self.ssh_user!r}, ssh_port={self.ssh_port}, "
            f"ssh_key={sentinel(self.ssh_key)}, "
            f"ssl_cert={sentinel(self.ssl_cert)}, "
            f"verify_ssl={self.verify_ssl}, protected={self.protected}, "
            f"default_app={self.default_app!r})"
        )

    def to_dict(self) -> dict[str, Any]:
        """TOML-serialisable dict (the name is the table key, not a field)."""
        return {
            "url": self.url,
            "token": self.token,
            "ssh_user": self.ssh_user,
            "ssh_port": self.ssh_port,
            "ssh_key": self.ssh_key,
            "ssl_cert": self.ssl_cert,
            "verify_ssl": self.verify_ssl,
            "protected": self.protected,
            "default_app": self.default_app,
        }

    @staticmethod
    def from_dict(name: str, data: dict[str, Any]) -> ServerRecord:
        """Build a ServerRecord from a TOML dict; defaults fill missing keys."""
        return ServerRecord(
            name=name,
            url=str(data.get("url") or ""),
            token=str(data.get("token") or ""),
            ssh_user=str(data.get("ssh_user") or "root"),
            ssh_port=int(data.get("ssh_port") or 22),
            ssh_key=str(data.get("ssh_key") or ""),
            ssl_cert=str(data.get("ssl_cert") or ""),
            verify_ssl=bool(data.get("verify_ssl", True)),
            protected=bool(data.get("protected")),
            default_app=str(data.get("default_app") or ""),
        )


@dataclass(frozen=True)
class ServerRegistry:
    """In-memory view of the server-binding registry.

    Holds the path the records were loaded from (for diagnostics and
    later writes) plus the materialised records by name. Frozen because
    the writer always returns a new instance after disk mutation —
    callers should never reach in and edit `records`.

    ``parse_error`` distinguishes the three load outcomes:
    - ``records={}, parse_error=None`` — file missing (fresh install)
    - ``records={...}, parse_error=None`` — file present and parsed OK
    - ``records={}, parse_error=<exc>`` — file present but unparseable.
      The migration refuses to clobber this; the CLI should surface
      "your servers.toml is broken — fix or delete it" rather than
      silently treating it as empty.
    """

    path: Path
    records: dict[str, ServerRecord] = field(default_factory=dict)
    parse_error: Exception | None = field(default=None, repr=False)

    def names(self) -> list[str]:
        """Server names in declaration order (TOML insertion order)."""
        return list(self.records.keys())

    def get(self, name: str) -> ServerRecord | None:
        return self.records.get(name)

    @property
    def is_broken(self) -> bool:
        """True iff the file on disk exists but failed to parse."""
        return self.parse_error is not None


def default_servers_path() -> Path:
    """Resolve the default ``~/.config/hop3-cli/servers.toml`` location.

    Uses ``platformdirs`` to match what the rest of the CLI uses for
    config discovery so behavior is consistent across platforms.
    """
    from platformdirs import user_config_dir  # noqa: PLC0415

    return Path(user_config_dir("hop3-cli", "Abilian SAS")) / SERVERS_TOML_FILENAME


def load_registry(path: Path | None = None) -> ServerRegistry:
    """Load the server registry from ``path`` (or the default location).

    Three load outcomes:
    - ``records={}, parse_error=None`` — file missing (fresh install).
      ``hop3 server add`` populates it.
    - ``records={...}, parse_error=None`` — file parsed OK.
    - ``records={}, parse_error=<exc>`` — file present but unparseable.
      Surfaced via ``ServerRegistry.is_broken`` so callers can refuse to
      clobber it.

    Skips malformed records (non-dict values) defensively so a partial
    parse doesn't crash.
    """
    target = path or default_servers_path()
    if not target.is_file():
        return ServerRegistry(path=target, records={})
    try:
        with target.open("rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return ServerRegistry(path=target, records={}, parse_error=exc)

    raw = data.get("servers", {})
    if not isinstance(raw, dict):
        return ServerRegistry(path=target, records={})

    records = {
        name: ServerRecord.from_dict(name, block)
        for name, block in raw.items()
        if isinstance(block, dict)
    }
    return ServerRegistry(path=target, records=records)


def save_registry(registry: ServerRegistry) -> Path:
    """Write the registry back to its path atomically and durably.

    Chmod 0o600 because the file stores the JWT auth token — other
    local users must not be able to read it. The chmod runs *after* the
    atomic rename, so there's no window during which the new file is
    world-readable.

    Returns the path written.
    """
    target = registry.path
    target.parent.mkdir(parents=True, exist_ok=True)
    data = {"servers": {name: rec.to_dict() for name, rec in registry.records.items()}}
    atomic_write_toml(target, data)
    # Tighten perms now that the file is in place. Some filesystems
    # (FAT-on-USB, certain WSL configs) reject chmod — treat as a soft
    # fail since the file is still in the user's config dir.
    import contextlib  # noqa: PLC0415

    with contextlib.suppress(OSError):
        os.chmod(target, 0o600)
    return target


def upsert(registry: ServerRegistry, record: ServerRecord) -> ServerRegistry:
    """Return a new registry with ``record`` inserted or replaced.

    Pure function — does NOT write to disk. Caller composes with
    ``save_registry`` to persist.
    """
    new_records = dict(registry.records)
    new_records[record.name] = record
    return ServerRegistry(path=registry.path, records=new_records)


def remove(registry: ServerRegistry, name: str) -> tuple[ServerRegistry, bool]:
    """Return ``(new_registry, removed)``.

    ``removed`` is True iff the name was present and dropped. Caller is
    responsible for persisting with ``save_registry`` and surfacing the
    "not found" case.
    """
    if name not in registry.records:
        return registry, False
    new_records = {k: v for k, v in registry.records.items() if k != name}
    return ServerRegistry(path=registry.path, records=new_records), True


def migrate_legacy_records(
    legacy_config_data: dict[str, Any],
    target: Path | None = None,
) -> tuple[ServerRegistry, list[str], list[str]]:
    """Build a fresh registry from legacy ``config.toml [contexts.*]`` data.

    Per ADR 042 §Migration, this is the one-shot rewriter run on first
    encounter of an unmigrated config. Each legacy ``[contexts.<name>]``
    becomes ``[servers.<name>]``. The legacy ``default_app`` field is
    preserved (ADR open question #6 settled in v0.2: server-level
    ``default_app`` lives on the server record as app-resolution
    source #8).

    Args:
        legacy_config_data: The parsed ``config.toml`` dict (e.g.
            ``Config.data``).
        target: Where the new registry will eventually be saved. Defaults
            to ``default_servers_path()``. Stored on the returned
            ``ServerRegistry`` so the caller can immediately
            ``save_registry(...)``.

    Returns:
        ``(registry, migrated_names, default_app_notes)`` where
        ``migrated_names`` is the names that were carried over, and
        ``default_app_notes`` is a list of one-line strings the caller
        should emit to stderr (one per legacy default_app retained, so
        operators see what was preserved and where).
    """
    legacy_contexts = legacy_config_data.get("contexts", {})
    if not isinstance(legacy_contexts, dict):
        return ServerRegistry(path=target or default_servers_path()), [], []

    records: dict[str, ServerRecord] = {}
    notes: list[str] = []
    for name, block in legacy_contexts.items():
        if not isinstance(block, dict):
            continue
        # The legacy field name is ``api_url``; the new field is ``url``.
        # Accept either to be forward+backward tolerant.
        normalised = dict(block)
        if "url" not in normalised and "api_url" in normalised:
            normalised["url"] = normalised["api_url"]
        if "token" not in normalised and "api_token" in normalised:
            normalised["token"] = normalised["api_token"]
        record = ServerRecord.from_dict(name, normalised)
        records[name] = record
        if record.default_app:
            notes.append(
                f"server {name!r} retained default_app={record.default_app!r}. "
                "Per-project [contexts.<n>].app overrides this if you "
                "prefer project-scoped pinning."
            )

    registry = ServerRegistry(
        path=target or default_servers_path(),
        records=records,
    )
    return registry, list(records.keys()), notes
