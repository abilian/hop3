# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# ruff:file-ignore[invalid-function-name] -- config properties are UPPER_SNAKE, mirroring hop3.config.HopConfig

"""Test Lab configuration.

A lazy, property-based singleton mirroring ``hop3.config.HopConfig``: settings
are read from the environment with typed defaults, and ``set_instance`` lets
tests swap the singleton.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

_TRUE = {"1", "true", "yes", "on"}


class TestlabConfig:
    """Global Test Lab runtime configuration (lazy singleton)."""

    _instance: TestlabConfig | None = None

    @classmethod
    def get_instance(cls) -> TestlabConfig:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def set_instance(cls, instance: TestlabConfig | None) -> None:
        """Swap (or clear) the singleton — for tests."""
        cls._instance = instance

    @property
    def DEBUG(self) -> bool:
        return os.environ.get("TESTLAB_DEBUG", "").lower() in _TRUE

    @property
    def DATABASE_URI(self) -> str:
        """Postgres DSN for the result store (``postgresql+psycopg://…``); empty
        means use the SQLite ``DB_PATH``. Set it for a server-resident deploy."""
        return os.environ.get("TESTLAB_DATABASE_URI", "")

    @property
    def DB_PATH(self) -> Path:
        """Path to the shared SQLite result store (used when DATABASE_URI is unset)."""
        default = Path.home() / ".hop3" / "test-results.db"
        return Path(os.environ.get("TESTLAB_DB_PATH", str(default)))

    @property
    def STORE_TARGET(self) -> str:
        """The result-store target — one value for read *and* write so the Lab and
        the engine never split across backends: the Postgres DSN when
        ``DATABASE_URI`` is set, else the SQLite ``DB_PATH``."""
        return self.DATABASE_URI or str(self.DB_PATH)

    @property
    def DATA_DIR(self) -> Path:
        """Base directory for this app instance's own data — keys, source clones,
        worktrees, artifacts.

        Per-app-instance, not a shared dotfile: a server-resident deploy points
        ``TESTLAB_DATA_DIR`` at ``/home/hop3/apps/<app>/data`` (see hop3.toml).
        Defaults to ``~/.hop3/testlab`` for local/dev use. (The SQLite result store
        is deliberately *not* here — it's shared with the engine; see ``DB_PATH``.)
        """
        default = Path.home() / ".hop3" / "testlab"
        return Path(os.environ.get("TESTLAB_DATA_DIR", str(default)))

    @property
    def ARTIFACT_DIR(self) -> Path:
        return Path(
            os.environ.get("TESTLAB_ARTIFACT_DIR", str(self.DATA_DIR / "artifacts"))
        )

    @property
    def KEYS_DIR(self) -> Path:
        """Directory where a credential's SSH private key is materialized (0600).

        Credentials live in the DB, but the engine subprocess (paramiko) needs the
        key as a *file path* — ``credentials.materialize_key`` writes it here and
        ``load_cloud_config`` hands the path to the run as ``ssh_key_path``.
        """
        return Path(os.environ.get("TESTLAB_KEYS_DIR", str(self.DATA_DIR / "keys")))

    @property
    def SOURCES_DIR(self) -> Path:
        """Per-source git clones (objects shared across refs)."""
        return self.DATA_DIR / "sources"

    @property
    def WORKSPACES_DIR(self) -> Path:
        """Per-ref checked-out worktrees the engine deploys from."""
        return self.DATA_DIR / "workspaces"

    # --- Auth (v1: the Lab's own single admin credential, ADR 044 OQ#7) ------
    @property
    def UNSAFE(self) -> bool:
        """Bypass the auth guard (tests/dev only). Off in production."""
        return os.environ.get("TESTLAB_UNSAFE", "").lower() in _TRUE

    @property
    def USERNAME(self) -> str:
        return os.environ.get("TESTLAB_USERNAME", "admin")

    @property
    def PASSWORD(self) -> str:
        """The admin password (plaintext env for v1; hash/secret store later)."""
        return os.environ.get("TESTLAB_PASSWORD", "")

    @property
    def SECRET_KEY(self) -> str:
        """HMAC secret for CSRF tokens.

        Stable per install so tokens survive a restart; set ``TESTLAB_SECRET_KEY``
        for a dedicated value. Falls back to one derived from the admin password
        (also per-install) so CSRF works out of the box without extra config.
        """
        explicit = os.environ.get("TESTLAB_SECRET_KEY")
        if explicit:
            return explicit
        seed = self.PASSWORD or "hop3-testlab-insecure-default"
        return hashlib.sha256(f"hop3-testlab-csrf:{seed}".encode()).hexdigest()
