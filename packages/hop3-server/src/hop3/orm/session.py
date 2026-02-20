# Copyright (c) 2024-2025, Abilian SAS
from __future__ import annotations

import os
from pathlib import Path

from advanced_alchemy.base import BigIntAuditBase
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from hop3 import config as c

# Global session factory cache
_session_factory_cache: dict[str, sessionmaker] = {}


def reset_session_factory_cache() -> None:
    """Reset the session factory cache (useful for testing)."""
    _session_factory_cache.clear()


def _configure_sqlite_engine(engine):
    """Configure SQLite-specific settings for better concurrency.

    Enables:
    - WAL mode: Allows concurrent reads during writes
    - Busy timeout: Wait up to 30 seconds when database is locked
    - Foreign keys: Enable foreign key constraint enforcement
    """

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
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
    """Create a SQLAlchemy session factory with automatic migrations.

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
    is_memory_sqlite = is_sqlite and ":memory:" in database_uri

    if is_sqlite:
        # SQLite-specific: allow multi-threaded access
        connect_args["check_same_thread"] = False

    # Pool configuration - only for file-based databases (not in-memory SQLite)
    if not is_memory_sqlite:
        if is_sqlite:
            # Use a small pool for SQLite (it doesn't handle concurrent writes well)
            engine_kwargs["pool_size"] = 1
            engine_kwargs["max_overflow"] = 0
        else:
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

    # Run Alembic migrations to ensure database schema is up-to-date
    alembic_ini_path = Path(__file__).parent / "alembic.ini"
    if alembic_ini_path.exists():
        alembic_cfg = AlembicConfig(str(alembic_ini_path))
        alembic_cfg.set_main_option("sqlalchemy.url", database_uri)

        # Upgrade to the latest revision
        with engine.begin() as conn:
            alembic_cfg.attributes["connection"] = conn
            command.upgrade(alembic_cfg, "head")
    else:
        # Fallback to create_all() if Alembic is not set up
        # This maintains backward compatibility during development
        # Use BigIntAuditBase.metadata to ensure all models are created
        with engine.begin() as conn:
            BigIntAuditBase.metadata.create_all(conn)

    session_factory = sessionmaker(bind=engine)
    _session_factory_cache[database_uri] = session_factory
    return session_factory
