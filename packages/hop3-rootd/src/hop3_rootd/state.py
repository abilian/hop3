# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: TRY003, EM102

"""Persistent state for hop3-rootd.

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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal

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


@dataclass(frozen=True)
class StoredRule:
    """One rule as persisted in state.json.

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


@dataclass(frozen=True)
class StoredCgroup:
    """One per-app cgroup leaf as persisted in state.json (ADR 046 §3 / P2.2).

    Records the kernel-form caps so reconcile can re-assert the leaf after a
    rootd restart. PIDs are *not* stored — they belong to the Emperor and are
    re-attached by hop3-server on the next deploy/reconcile.
    """

    app_name: str
    memory_max: int | None
    cpu_max: str | None
    pids_max: int | None
    applied_at: str


@dataclass(frozen=True)
class StoredMount:
    """One volume mount as persisted in state.json (ADR 046 §2 / P2.1).

    ``type`` is ``"tmpfs"`` or ``"bind"``; ``source`` is the host path for a
    bind, None for tmpfs. Identified by (app_name, target).
    """

    app_name: str
    target: str
    type: str
    source: str | None
    applied_at: str


@dataclass(frozen=True)
class StoredProxy:
    """One addon-exposure TCP forwarder as persisted in state.json.

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


@dataclass
class State:
    """In-memory snapshot of rootd's persistent state.

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
            "rules": [
                {
                    "rule_id": r.rule_id,
                    "spec": r.spec,
                    "applied_at": r.applied_at,
                    "status": r.status,
                }
                for r in self.rules
            ],
            "cgroups": [
                {
                    "app_name": c.app_name,
                    "memory_max": c.memory_max,
                    "cpu_max": c.cpu_max,
                    "pids_max": c.pids_max,
                    "applied_at": c.applied_at,
                }
                for c in self.cgroups
            ],
            "mounts": [
                {
                    "app_name": m.app_name,
                    "target": m.target,
                    "type": m.type,
                    "source": m.source,
                    "applied_at": m.applied_at,
                }
                for m in self.mounts
            ],
            "proxies": [
                {
                    "addon_type": p.addon_type,
                    "addon_name": p.addon_name,
                    "unit": p.unit,
                    "public_port": p.public_port,
                    "target_port": p.target_port,
                    "source": p.source,
                    "applied_at": p.applied_at,
                }
                for p in self.proxies
            ],
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


def _parse_rules(obj: dict[str, Any]) -> list[StoredRule]:
    """Extract and validate the 'rules' list. Raises on any malformed entry."""
    rules_raw: list[Any] = obj.get("rules", [])
    if not isinstance(rules_raw, list):
        raise StateCorruptError(
            f"'rules' must be a list, got {type(rules_raw).__name__}"
        )

    rules: list[StoredRule] = []
    for i, r in enumerate(rules_raw):
        if not isinstance(r, dict):
            raise StateCorruptError(f"rules[{i}] must be an object")
        try:
            rules.append(
                StoredRule(
                    rule_id=str(r["rule_id"]),
                    spec=dict(r["spec"]),
                    applied_at=str(r["applied_at"]),
                    status=_coerce_status(r.get("status", "applied"), i),
                )
            )
        except (KeyError, TypeError) as e:
            raise StateCorruptError(f"rules[{i}] is malformed: {e}") from e
    return rules


def _parse_cgroups(obj: dict[str, Any]) -> list[StoredCgroup]:
    """Extract the optional 'cgroups' list. Absent (old v1 files) → []."""
    raw: list[Any] = obj.get("cgroups", [])
    if not isinstance(raw, list):
        raise StateCorruptError(f"'cgroups' must be a list, got {type(raw).__name__}")

    cgroups: list[StoredCgroup] = []
    for i, c in enumerate(raw):
        if not isinstance(c, dict):
            raise StateCorruptError(f"cgroups[{i}] must be an object")
        try:
            cgroups.append(
                StoredCgroup(
                    app_name=str(c["app_name"]),
                    memory_max=c.get("memory_max"),
                    cpu_max=c.get("cpu_max"),
                    pids_max=c.get("pids_max"),
                    applied_at=str(c["applied_at"]),
                )
            )
        except (KeyError, TypeError) as e:
            raise StateCorruptError(f"cgroups[{i}] is malformed: {e}") from e
    return cgroups


def _parse_mounts(obj: dict[str, Any]) -> list[StoredMount]:
    """Extract the optional 'mounts' list. Absent (old v1 files) → []."""
    raw: list[Any] = obj.get("mounts", [])
    if not isinstance(raw, list):
        raise StateCorruptError(f"'mounts' must be a list, got {type(raw).__name__}")

    mounts: list[StoredMount] = []
    for i, m in enumerate(raw):
        if not isinstance(m, dict):
            raise StateCorruptError(f"mounts[{i}] must be an object")
        try:
            mounts.append(
                StoredMount(
                    app_name=str(m["app_name"]),
                    target=str(m["target"]),
                    type=str(m["type"]),
                    source=m.get("source"),
                    applied_at=str(m["applied_at"]),
                )
            )
        except (KeyError, TypeError) as e:
            raise StateCorruptError(f"mounts[{i}] is malformed: {e}") from e
    return mounts


def _parse_proxies(obj: dict[str, Any]) -> list[StoredProxy]:
    """Extract the optional 'proxies' list. Absent (older v1 files) → []."""
    raw: list[Any] = obj.get("proxies", [])
    if not isinstance(raw, list):
        raise StateCorruptError(f"'proxies' must be a list, got {type(raw).__name__}")

    proxies: list[StoredProxy] = []
    for i, p in enumerate(raw):
        if not isinstance(p, dict):
            raise StateCorruptError(f"proxies[{i}] must be an object")
        try:
            proxies.append(
                StoredProxy(
                    addon_type=str(p["addon_type"]),
                    addon_name=str(p["addon_name"]),
                    unit=str(p["unit"]),
                    public_port=int(p["public_port"]),
                    target_port=int(p["target_port"]),
                    source=str(p.get("source", "any")),
                    applied_at=str(p["applied_at"]),
                )
            )
        except (KeyError, TypeError, ValueError) as e:
            raise StateCorruptError(f"proxies[{i}] is malformed: {e}") from e
    return proxies


def _coerce_status(value: Any, index: int) -> RuleStatus:
    """Validate that a stored status value is one of RuleStatus's literals."""
    if value not in {"applied", "pending", "removing"}:
        raise StateCorruptError(
            f"rules[{index}] has invalid status {value!r}; "
            "expected 'applied', 'pending', or 'removing'"
        )
    return value


def load(path: Path = DEFAULT_STATE_PATH) -> State:
    """Read and parse state.json. Strict — any error is fatal.

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
    rules = _parse_rules(obj)
    cgroups = _parse_cgroups(obj)
    mounts = _parse_mounts(obj)
    proxies = _parse_proxies(obj)
    return State(
        version=version, rules=rules, cgroups=cgroups, mounts=mounts, proxies=proxies
    )


def save(state: State, path: Path = DEFAULT_STATE_PATH) -> None:
    """Atomic write of state.json (tmp + fsync + rename + chmod 0o600).

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
