# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Persistent state for hop3-rootd.

Currently a single JSON file at /var/lib/hop3-rootd/state.json holding
the list of firewall rules rootd thinks should exist.

Atomic-write recipe (write to .tmp, fsync, rename) per ADR 041 §13.
Corrupt or missing → daemon refuses to start.

Schema version is in the file (`{"version": 1, "rules": [...]}`).
Future migration is out of scope; an unknown version is a hard error.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal, cast

RuleStatus = Literal["applied", "pending", "removing"]

# --- Defaults -------------------------------------------------------------

DEFAULT_STATE_PATH: Final[Path] = Path("/var/lib/hop3-rootd/state.json")

STATE_VERSION: Final[int] = 1


# --- Exceptions -----------------------------------------------------------


class StateError(Exception):
    """Base class for state-loading / -saving errors."""


class StateMissingError(StateError):
    """state.json doesn't exist on disk."""


class StateCorruptError(StateError):
    """state.json couldn't be parsed or is structurally invalid."""


class StateVersionError(StateError):
    """state.json version isn't one we know how to handle."""


# --- Typed entries --------------------------------------------------------
#
# Each Stored* owns its own (de)serialisation: the field list appears once,
# next to the type it describes, so a new field is added in one place rather
# than in three (dataclass + State.to_dict + _parse_*). load()/save() below
# are generic loops over these methods.


def _coerce_status(value: object, path: str) -> RuleStatus:
    """Validate that a stored status value is one of RuleStatus's literals."""
    if value not in {"applied", "pending", "removing"}:
        raise StateCorruptError(
            f"{path} has invalid status {value!r}; "
            "expected 'applied', 'pending', or 'removing'"
        )
    return cast("RuleStatus", value)


@dataclass(frozen=True)
class StoredRule:
    """
    One rule as persisted in state.json.

    Fields:
        rule_id: rootd-stable UUID4 (caller-visible identifier).
        spec: the original request args (validated PortSpec serialised).
        applied_at: ISO-8601 timestamp when the rule was added to the kernel.
        status: "applied" (in kernel) | "pending" (mid-add) | "removing" (mid-remove).
    """

    rule_id: str
    spec: dict[str, Any]
    applied_at: str
    status: RuleStatus = "applied"

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "spec": self.spec,
            "applied_at": self.applied_at,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, raw: object, path: str) -> StoredRule:
        if not isinstance(raw, dict):
            raise StateCorruptError(f"{path} must be an object")
        try:
            return cls(
                rule_id=str(raw["rule_id"]),
                spec=dict(raw["spec"]),
                applied_at=str(raw["applied_at"]),
                status=_coerce_status(raw.get("status", "applied"), path),
            )
        except (KeyError, TypeError) as e:
            raise StateCorruptError(f"{path} is malformed: {e}") from e


@dataclass(frozen=True)
class StoredCgroup:
    """
    One per-app cgroup leaf as persisted in state.json (ADR 046 §3 / P2.2).

    Records the kernel-form caps so reconcile can re-assert the leaf after a
    rootd restart. PIDs are *not* stored — they belong to the Emperor and are
    re-attached by hop3-server on the next deploy/reconcile.
    """

    app_name: str
    memory_max: int | None
    cpu_max: str | None
    pids_max: int | None
    applied_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_name": self.app_name,
            "memory_max": self.memory_max,
            "cpu_max": self.cpu_max,
            "pids_max": self.pids_max,
            "applied_at": self.applied_at,
        }

    @classmethod
    def from_dict(cls, raw: object, path: str) -> StoredCgroup:
        if not isinstance(raw, dict):
            raise StateCorruptError(f"{path} must be an object")
        try:
            return cls(
                app_name=str(raw["app_name"]),
                memory_max=raw.get("memory_max"),
                cpu_max=raw.get("cpu_max"),
                pids_max=raw.get("pids_max"),
                applied_at=str(raw["applied_at"]),
            )
        except (KeyError, TypeError) as e:
            raise StateCorruptError(f"{path} is malformed: {e}") from e


@dataclass(frozen=True)
class StoredMount:
    """
    One volume mount as persisted in state.json (ADR 046 §2 / P2.1).

    ``type`` is ``"tmpfs"`` or ``"bind"``; ``source`` is the host path for a
    bind, None for tmpfs. Identified by (app_name, target).
    """

    app_name: str
    target: str
    type: str
    source: str | None
    applied_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_name": self.app_name,
            "target": self.target,
            "type": self.type,
            "source": self.source,
            "applied_at": self.applied_at,
        }

    @classmethod
    def from_dict(cls, raw: object, path: str) -> StoredMount:
        if not isinstance(raw, dict):
            raise StateCorruptError(f"{path} must be an object")
        try:
            return cls(
                app_name=str(raw["app_name"]),
                target=str(raw["target"]),
                type=str(raw["type"]),
                source=raw.get("source"),
                applied_at=str(raw["applied_at"]),
            )
        except (KeyError, TypeError) as e:
            raise StateCorruptError(f"{path} is malformed: {e}") from e


@dataclass(frozen=True)
class StoredProxy:
    """
    One addon-exposure TCP forwarder as persisted in state.json.

    A ``systemd-socket-proxyd`` unit pair forwarding ``0.0.0.0:public_port`` →
    ``127.0.0.1:target_port`` for an addon. Identified by (addon_type,
    addon_name); ``unit`` is the base systemd unit name. ``source`` is the
    access scope (the firewall is the real enforcer) kept for diagnostics.
    """

    addon_type: str
    addon_name: str
    unit: str
    public_port: int
    target_port: int
    source: str
    applied_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "addon_type": self.addon_type,
            "addon_name": self.addon_name,
            "unit": self.unit,
            "public_port": self.public_port,
            "target_port": self.target_port,
            "source": self.source,
            "applied_at": self.applied_at,
        }

    @classmethod
    def from_dict(cls, raw: object, path: str) -> StoredProxy:
        if not isinstance(raw, dict):
            raise StateCorruptError(f"{path} must be an object")
        try:
            return cls(
                addon_type=str(raw["addon_type"]),
                addon_name=str(raw["addon_name"]),
                unit=str(raw["unit"]),
                public_port=int(raw["public_port"]),
                target_port=int(raw["target_port"]),
                source=str(raw.get("source", "any")),
                applied_at=str(raw["applied_at"]),
            )
        except (KeyError, TypeError, ValueError) as e:
            raise StateCorruptError(f"{path} is malformed: {e}") from e


@dataclass
class State:
    """
    In-memory snapshot of rootd's persistent state.

    Mutable on purpose — the daemon updates it as ops apply. Use `to_dict`
    when persisting.
    """

    version: int = STATE_VERSION
    rules: list[StoredRule] = field(default_factory=list)
    cgroups: list[StoredCgroup] = field(default_factory=list)
    mounts: list[StoredMount] = field(default_factory=list)
    proxies: list[StoredProxy] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "rules": [r.to_dict() for r in self.rules],
            "cgroups": [c.to_dict() for c in self.cgroups],
            "mounts": [m.to_dict() for m in self.mounts],
            "proxies": [p.to_dict() for p in self.proxies],
        }

    def find_rule(self, rule_id: str) -> StoredRule | None:
        """Return the rule with the given id, or None."""
        for r in self.rules:
            if r.rule_id == rule_id:
                return r
        return None

    def rules_for_app(self, app_name: str) -> list[StoredRule]:
        return [r for r in self.rules if r.spec.get("app_name") == app_name]

    def mounts_for_app(self, app_name: str) -> list[StoredMount]:
        return [m for m in self.mounts if m.app_name == app_name]


# --- Load / save ----------------------------------------------------------


def _parse_version(obj: dict[str, Any], path: Path) -> int:
    """Extract and validate the 'version' field. Raises on any error."""
    version = obj.get("version")
    if version is None:
        raise StateVersionError(f"missing 'version' field in {path}")
    if not isinstance(version, int):
        raise StateVersionError(f"'version' must be int, got {type(version).__name__}")
    if version != STATE_VERSION:
        raise StateVersionError(
            f"unknown state version {version} (this daemon supports {STATE_VERSION})"
        )
    return version


def _parse_entries(
    raw: object, name: str, parse: Callable[[Any, str], Any]
) -> list[Any]:
    """
    Validate ``raw`` is a list, then build each entry via ``parse(item, path)``.

    ``path`` passed to ``parse`` is ``"<name>[<i>]"`` so corruption errors name
    the exact entry (e.g. ``"rules[2] is malformed"``).
    """
    if not isinstance(raw, list):
        raise StateCorruptError(f"{name!r} must be a list, got {type(raw).__name__}")
    return [parse(item, f"{name}[{i}]") for i, item in enumerate(raw)]


def load(path: Path = DEFAULT_STATE_PATH) -> State:
    """
    Read and parse state.json. Strict — any error is fatal.

    Raises:
        StateMissingError: file does not exist.
        StateCorruptError: file is not valid JSON or structurally wrong.
        StateVersionError: version field is missing or unknown.
    """
    if not path.exists():
        raise StateMissingError(f"state file not found: {path}")

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise StateCorruptError(f"could not read {path}: {e}") from e

    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        raise StateCorruptError(f"invalid JSON in {path}: {e}") from e

    if not isinstance(obj, dict):
        raise StateCorruptError(f"top-level must be object, got {type(obj).__name__}")

    version = _parse_version(obj, path)
    rules = _parse_entries(obj.get("rules", []), "rules", StoredRule.from_dict)
    cgroups = _parse_entries(obj.get("cgroups", []), "cgroups", StoredCgroup.from_dict)
    mounts = _parse_entries(obj.get("mounts", []), "mounts", StoredMount.from_dict)
    proxies = _parse_entries(obj.get("proxies", []), "proxies", StoredProxy.from_dict)
    return State(
        version=version, rules=rules, cgroups=cgroups, mounts=mounts, proxies=proxies
    )


def save(state: State, path: Path = DEFAULT_STATE_PATH) -> None:
    """
    Atomic write of state.json (tmp + fsync + rename + chmod 0o600).

    The chmod pins file perms regardless of umask — the StateDirectory
    already gates external access in production, but standalone /
    test runs benefit from the explicit cap. See notes/security.md
    §3.4 for the broader rationale.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(state.to_dict(), indent=2, sort_keys=True)

    with tmp.open("w", encoding="utf-8") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())

    # Atomic rename. On POSIX, rename within the same filesystem is atomic.
    tmp.replace(path)
    os.chmod(path, 0o600)


def init_empty(path: Path = DEFAULT_STATE_PATH) -> State:
    """Create a fresh empty state.json. Used by the installer at fresh-install."""
    state = State(version=STATE_VERSION, rules=[])
    save(state, path)
    return state
