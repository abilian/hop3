# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Cloud credentials (Hetzner + SSH) for the worker.

Precedence (ADR 044; matches the existing hop3-testing config mechanism):

1. a ``config.toml`` file (values may be literals or ``$ENV_VAR`` references),
2. environment variables (12-factor) for any value the file leaves unset,
3. built-in defaults.

The file is discovered at ``$TESTLAB_CONFIG`` → ``~/.hop3/testlab/config.toml`` →
``./config.toml``. It holds secrets, so it is gitignored (see config.toml.example).
A UI-managed source can be layered on later.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import tomllib
from hop3_testing.system_tests.config import HetznerConfig

from hop3_testlab.config import TestlabConfig


@dataclass(frozen=True)
class CloudConfig:
    """Resolved cloud credentials for a worker run."""

    hetzner_token: str
    hetzner_server_id: int
    hetzner_image: str
    ssh_key_path: str | None
    # Name of the SSH key registered with Hetzner; re-injected on rebuild.
    # Required for the blank-slate rebuild (without it a rebuild locks us out).
    hetzner_ssh_key_name: str | None = None

    @property
    def is_complete(self) -> bool:
        """True when there's enough to attempt a Hetzner run."""
        return bool(self.hetzner_token and self.hetzner_server_id)


def _resolve_ref(value: str, env: dict[str, str]) -> str:
    """Resolve a ``$VAR`` / ``${VAR}`` reference against the environment."""
    if value.startswith("$"):
        name = value[1:]
        if name.startswith("{") and name.endswith("}"):
            name = name[1:-1]
        return env.get(name, "")
    return value


def _discover() -> Path | None:
    # $TESTLAB_CONFIG is authoritative when set (use it or nothing) — so it can
    # also point tests away from the developer's ~/.hop3/testlab/config.toml.
    explicit = os.environ.get("TESTLAB_CONFIG")
    if explicit:
        path = Path(explicit)
        return path if path.is_file() else None
    for candidate in (
        Path.home() / ".hop3" / "testlab" / "config.toml",
        Path("config.toml"),
    ):
        if candidate.is_file():
            return candidate
    return None


def _db_hetzner() -> tuple[dict, str | None] | None:
    """
    The active Hetzner credential from the DB as ``(hetzner_dict, ssh_key_path)``.

    Returns ``None`` when there's no credential row, so ``load_cloud_config`` falls
    back to the file/env chain (the path manual ``hop3-test`` still uses). Imports
    are local: the worker imports this module early and the DB stack is heavy.
    """
    from hop3_testlab.credentials import (  # ruff:ignore[import-outside-top-level]
        materialize_key,
    )
    from hop3_testlab.db import (  # ruff:ignore[import-outside-top-level]
        get_session_factory,
    )
    from hop3_testlab.repositories import (  # ruff:ignore[import-outside-top-level]
        CredentialsRepository,
    )

    factory = get_session_factory(TestlabConfig.get_instance().STORE_TARGET)
    with factory() as session:
        cred = CredentialsRepository(session).active("hetzner")
        if cred is None:
            return None
        data = {
            "api_token": cred.api_token,
            "server_id": cred.server_id or "",
            "image": cred.image,
            "ssh_key_name": cred.ssh_key_name,
        }
        key = materialize_key(cred.name, cred.private_key)
    return data, (str(key) if key else None)


def load_cloud_config(path: Path | None = None) -> CloudConfig:
    """
    Resolve cloud config: the active DB credential wins, else config.toml → env.

    A server-resident Lab is configured via the dashboard (DB credentials). With no
    credential row — e.g. manual ``hop3-test`` on a laptop — it falls back to the
    discovered file then env, unchanged.
    """
    env = dict(os.environ)
    db = _db_hetzner()
    if db is not None:
        hetzner_data, key_path = db
        hetzner = HetznerConfig.from_dict(hetzner_data, env)
    else:
        data = _load_data(path)
        # HetznerConfig.from_dict resolves $refs and falls back to env for
        # api_token / server_id, so the file→env→default chain is reused.
        hetzner = HetznerConfig.from_dict(data.get("hetzner", {}), env)
        ssh = data.get("ssh", {})
        key_path = (
            _resolve_ref(str(ssh.get("key_path", "")), env)
            or env.get("HOP3_TEST_SSH_KEY", "")
            or None
        )

    return CloudConfig(
        hetzner_token=hetzner.api_token,
        hetzner_server_id=hetzner.server_id,
        hetzner_image=hetzner.image,
        ssh_key_path=key_path or None,
        hetzner_ssh_key_name=hetzner.ssh_key_name
        or env.get("HETZNER_SSH_KEY_NAME")
        or None,
    )


DEFAULT_KEEP_RUNS = 30


def load_retention(path: Path | None = None) -> int:
    """
    Build-log retention: how many recent runs to keep (config.toml [retention]).

    ``[retention].keep_runs`` in the config file, else $TESTLAB_LOG_RETENTION_RUNS,
    else :data:`DEFAULT_KEEP_RUNS`.
    """
    data = _load_data(path)

    raw = data.get("retention", {}).get("keep_runs")
    if isinstance(raw, str):
        raw = _resolve_ref(raw, dict(os.environ)) or None
    if raw is None:
        raw = os.environ.get("TESTLAB_LOG_RETENTION_RUNS")
    try:
        return int(raw) if raw else DEFAULT_KEEP_RUNS
    except (TypeError, ValueError):
        return DEFAULT_KEEP_RUNS


@dataclass(frozen=True)
class ScheduleConfig:
    """Nightly scheduler settings: when to fire, and which profile to enqueue."""

    enabled: bool
    hour: int
    minute: int
    profile: str | None  # build profile the nightly enqueues (None -> idle)


_TRUE = {"1", "true", "yes", "on"}


def _as_bool(*values) -> bool:
    """First non-empty value coerced to bool (toml bool or env string)."""
    for value in values:
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip():
            return value.strip().lower() in _TRUE
    return False


def load_schedule(path: Path | None = None) -> ScheduleConfig:
    """
    Nightly scheduler config: [schedule] in config.toml, then env, then defaults.

    Disabled by default so dev `serve` never fires a real run; production enables
    it via ``[schedule].enabled = true``.
    """
    data = _load_data(path).get("schedule", {})
    env = os.environ
    return ScheduleConfig(
        enabled=_as_bool(data.get("enabled"), env.get("TESTLAB_SCHEDULE_ENABLED")),
        hour=int(data.get("hour", env.get("TESTLAB_SCHEDULE_HOUR", 0))),
        minute=int(data.get("minute", env.get("TESTLAB_SCHEDULE_MINUTE", 0))),
        profile=data.get("profile") or env.get("TESTLAB_SCHEDULE_PROFILE") or None,
    )


def _load_data(path: Path | None) -> dict:
    """Load the discovered (or given) config.toml as a dict ({} if none)."""
    if path is None:
        path = _discover()
    if path is not None and path.is_file():
        with path.open("rb") as f:
            return tomllib.load(f)
    return {}
