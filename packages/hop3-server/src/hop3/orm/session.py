# Copyright (c) 2024-2025, Abilian SAS
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from hop3 import config as c

from .app import App


def get_session_factory(database_uri: str = "") -> sessionmaker:
    """Create a SQLAlchemy session factory with automatic migrations.

    This function:
    1. Creates the database engine
    2. Runs Alembic migrations to upgrade the schema to the latest version
    3. Returns a sessionmaker for creating database sessions

    Args:
        database_uri: SQLAlchemy database URL. Defaults to SQLite in HOP3_ROOT.

    Returns:
        A sessionmaker instance bound to the database engine.

    Note:
        Instead of using create_all(), this function uses Alembic migrations
        to manage schema changes. This ensures proper versioning and rollback
        capabilities for production upgrades.
    """
    if not database_uri:
        database_uri = f"sqlite:///{c.HOP3_ROOT}/hop3.db"

    engine = create_engine(database_uri)

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
        with engine.begin() as conn:
            App.metadata.create_all(conn)

    return sessionmaker(bind=engine)
