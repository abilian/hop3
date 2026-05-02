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


@dataclass
class State:
    """In-memory snapshot of rootd's persistent state.

    Mutable on purpose — the daemon updates it as ops apply. Use `to_dict`
    when persisting.
    """

    version: int = STATE_VERSION
    rules: list[StoredRule] = field(default_factory=list)

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
        }

    def find_rule(self, rule_id: str) -> StoredRule | None:
        """Return the rule with the given id, or None."""
        for r in self.rules:
            if r.rule_id == rule_id:
                return r
        return None

    def rules_for_app(self, app_name: str) -> list[StoredRule]:
        return [r for r in self.rules if r.spec.get("app_name") == app_name]


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
    rules_raw = obj.get("rules", [])
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
                    status=str(r.get("status", "applied")),
                )
            )
        except (KeyError, TypeError) as e:
            raise StateCorruptError(f"rules[{i}] is malformed: {e}") from e
    return rules


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
    return State(version=version, rules=rules)


def save(state: State, path: Path = DEFAULT_STATE_PATH) -> None:
    """Atomic write of state.json: tmp + fsync + rename.

    The pattern guarantees:
      - never observe a half-written file (rename is atomic on POSIX)
      - never observe a stale file after success (fsync before rename
        ensures the new bytes are durable on disk before the rename)
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


def init_empty(path: Path = DEFAULT_STATE_PATH) -> State:
    """Create a fresh empty state.json. Used by the installer at fresh-install."""
    state = State(version=STATE_VERSION, rules=[])
    save(state, path)
    return state
