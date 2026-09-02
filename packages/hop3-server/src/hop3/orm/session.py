# Copyright (c) 2024-2025, Abilian SAS
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from advanced_alchemy.base import BigIntAuditBase
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, event, inspect as sa_inspect
from sqlalchemy.orm import sessionmaker

from hop3 import config as c

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine
    from sqlalchemy.engine.interfaces import DBAPIConnection

# Global session factory cache
_session_factory_cache: dict[str, sessionmaker] = {}


def reset_session_factory_cache() -> None:
    """Reset the session factory cache (useful for testing)."""
    _session_factory_cache.clear()


def _configure_sqlite_engine(engine: Engine) -> None:
    """
    Configure SQLite-specific settings for better concurrency.

    Enables:
    - WAL mode: Allows concurrent reads during writes
    - Busy timeout: Wait up to 30 seconds when database is locked
    - Foreign keys: Enable foreign key constraint enforcement
    """

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(
        dbapi_connection: DBAPIConnection, connection_record: object
    ) -> None:
        cursor = dbapi_connection.cursor()
        # Enable WAL mode for better concurrent access
        cursor.execute("PRAGMA journal_mode=WAL")
        # Wait up to 30 seconds when database is locked
        cursor.execute("PRAGMA busy_timeout=30000")
        # Enable foreign key constraints
        cursor.execute("PRAGMA foreign_keys=ON")
        # Synchronous mode: NORMAL is a good balance of safety and speed
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


def get_session_factory(database_uri: str = "") -> sessionmaker:
    """
    Create a SQLAlchemy session factory with automatic migrations.

    This function:
    1. Creates the database engine
    2. Runs Alembic migrations to upgrade the schema to the latest version
    3. Returns a sessionmaker for creating database sessions
    4. Caches session factories by database URI for performance

    Args:
        database_uri: SQLAlchemy database URL. Defaults to SQLite in HOP3_ROOT.
                     Can be overridden via HOP3_DATABASE_URI environment variable.

    Returns:
        A sessionmaker instance bound to the database engine.

    Note:
        Instead of using create_all(), this function uses Alembic migrations
        to manage schema changes. This ensures proper versioning and rollback
        capabilities for production upgrades.

        For testing, use reset_session_factory_cache() to clear the cache.
        You can also set HOP3_DATABASE_URI=sqlite:///:memory: for in-memory tests.
    """
    if not database_uri:
        # Check for environment variable override (useful for testing)
        database_uri = os.environ.get("HOP3_DATABASE_URI", "")
        if not database_uri:
            database_uri = f"sqlite:///{c.HOP3_ROOT}/hop3.db"

    # Return cached factory if available
    if database_uri in _session_factory_cache:
        return _session_factory_cache[database_uri]

    # Configure engine with appropriate settings
    connect_args = {}
    engine_kwargs = {}

    is_sqlite = database_uri.startswith("sqlite")
    # SQLite names an in-memory database two ways, and both must be detected:
    # the classic `:memory:` and the URI form `?mode=memory` (which the xdist
    # test fixtures use, one DB per worker). Matching only the first left
    # SQLAlchemy choosing SingletonThreadPool for a `mode=memory` URI while we
    # passed it pool_size/max_overflow, so `pytest -n auto` died at
    # create_engine with "Invalid argument(s) 'max_overflow'".
    is_memory_sqlite = is_sqlite and (
        ":memory:" in database_uri or "mode=memory" in database_uri
    )

    if is_sqlite:
        # SQLite-specific: allow multi-threaded access
        connect_args["check_same_thread"] = False

    # Pool configuration - only for file-based databases (not in-memory SQLite)
    if not is_memory_sqlite:
        # SQLite gets the same pool as PostgreSQL. The earlier ``pool_size=1``
        # was over-conservative: it serialized ALL database access — reads
        # included — through a single connection. A deployment runs in a
        # background thread (commands/app.py::_deploy_streaming) that holds
        # its session/connection open for the entire multi-minute build, so
        # with one connection every concurrent request (notably auth token
        # verification, which is a read) queued behind it and timed out after
        # ``pool_timeout`` (30s) — surfacing as bogus 401s on /rpc and 302s on
        # /api/stream during heavy deploys.
        #
        # WAL mode (enabled in _configure_sqlite_engine) lets readers proceed
        # concurrently with a writer, so a real pool is safe: auth reads get
        # their own connection and never block behind a deploy's write
        # transaction. Writer-vs-writer contention (rare; deploys are
        # typically sequential) is handled by busy_timeout=30000.
        engine_kwargs["pool_size"] = 5
        engine_kwargs["max_overflow"] = 10
        engine_kwargs["pool_pre_ping"] = True  # Verify connections are alive

    engine = create_engine(
        database_uri,
        connect_args=connect_args,
        **engine_kwargs,
    )

    # Configure SQLite-specific PRAGMAs (not needed for in-memory test databases)
    if is_sqlite and not is_memory_sqlite:
        _configure_sqlite_engine(engine)

    # Schema bootstrap.
    #
    # We deliberately do NOT run migrations here. Migrations are applied
    # explicitly and gated by `hop3-server db:upgrade` during deploy (so a
    # schema change aborts the deploy with the OLD server still running).
    # Auto-migrating on every boot/CLI invocation would undermine that gate
    # and risk concurrent runs racing on the version table.
    #
    # This step only ensures a brand-new database has its tables, and stamps
    # it at head so Alembic is consistent from birth (create_all produces the
    # current = head schema). An EXISTING database is left untouched: an
    # unstamped/pre-Alembic one is adopted later, safely, by `db:upgrade`.
    with engine.begin() as conn:
        if not sa_inspect(conn).has_table("app"):
            BigIntAuditBase.metadata.create_all(conn)
            # Stamp head for real (persistent) databases. In-memory test DBs
            # are ephemeral and never deployed, so stamping them is pointless
            # and we keep their behavior identical to before (create_all only).
            if not is_memory_sqlite:
                alembic_cfg = _bootstrap_alembic_config(database_uri)
                if alembic_cfg is not None:
                    alembic_cfg.attributes["connection"] = conn
                    command.stamp(alembic_cfg, "head")

    session_factory = sessionmaker(bind=engine)
    _session_factory_cache[database_uri] = session_factory
    return session_factory


def _bootstrap_alembic_config(database_uri: str) -> AlembicConfig | None:
    """
    Build an Alembic Config pointing at the bundled alembic.ini.

    Resolves the path from the ``hop3`` package root (where alembic.ini
    actually ships) rather than relative to this module. Returns None if it
    can't be found, so a fresh DB still gets its schema via create_all even
    when Alembic isn't packaged alongside (e.g. odd test layouts).
    """
    import hop3  # ruff:ignore[import-outside-top-level]

    ini_path = Path(hop3.__file__).parent / "alembic.ini"
    if not ini_path.exists():
        return None
    cfg = AlembicConfig(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", database_uri)
    return cfg
