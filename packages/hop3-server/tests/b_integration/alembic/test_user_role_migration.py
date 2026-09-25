# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The user-role migration carries a 0.7 server's accounts onto standard roles.

Before ADR 061, roles were rows in ``sec_role`` joined through
``sec_users_roles``, and only ``admin`` ever existed there. The migration must
keep every admin an admin and give every other account ``deployer``, which is
what it could already do. It runs here on tables shaped as 0.7 created them.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

import hop3

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import ModuleType

    from sqlalchemy.engine import Connection

# The three tables as the 0.7 models created them (SQLite).
OLD_SCHEMA = [
    """CREATE TABLE sec_user (
        id INTEGER NOT NULL PRIMARY KEY,
        email VARCHAR(255) NOT NULL UNIQUE,
        username VARCHAR(80) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL,
        last_login_at DATETIME, current_login_at DATETIME,
        last_login_ip VARCHAR(45) NOT NULL, current_login_ip VARCHAR(45) NOT NULL,
        login_count INTEGER NOT NULL, active BOOLEAN NOT NULL,
        confirmed_at DATETIME,
        created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)""",
    """CREATE TABLE sec_role (
        id INTEGER NOT NULL PRIMARY KEY,
        name VARCHAR(80) NOT NULL UNIQUE, description VARCHAR(255) NOT NULL,
        created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)""",
    """CREATE TABLE sec_users_roles (
        user_id BIGINT NOT NULL REFERENCES sec_user (id),
        role_id BIGINT NOT NULL REFERENCES sec_role (id),
        PRIMARY KEY (user_id, role_id))""",
]


def _load_migration() -> ModuleType:
    path = (
        Path(hop3.__file__).parent
        / "alembic"
        / "versions"
        / "b9caf947fe56_user_role.py"
    )
    spec = importlib.util.spec_from_file_location("mig_user_role", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(conn: Connection, step: str) -> None:
    """Run the migration's ``upgrade`` or ``downgrade`` against ``conn``."""
    migration = _load_migration()
    with Operations.context(MigrationContext.configure(conn)):
        getattr(migration, step)()


def _add_user(conn: Connection, user_id: int, username: str) -> None:
    conn.execute(
        text(
            "INSERT INTO sec_user (id, email, username, password_hash, "
            "last_login_ip, current_login_ip, login_count, active, "
            "created_at, updated_at) VALUES (:id, :email, :username, '', '', '', "
            "0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
        {"id": user_id, "email": f"{username}@example.com", "username": username},
    )


@pytest.fixture
def old_server() -> Iterator[Connection]:
    """
    A 0.7 control-plane database with one admin and two ordinary accounts.

    ``carol`` holds a role row named something other than ``admin``, which the
    old code never created but the old schema allowed: only ``admin`` maps.
    """
    engine = create_engine("sqlite://")
    with engine.connect() as conn:
        for ddl in OLD_SCHEMA:
            conn.exec_driver_sql(ddl)
        for user_id, username in ((1, "alice"), (2, "bob"), (3, "carol")):
            _add_user(conn, user_id, username)
        conn.execute(
            text(
                "INSERT INTO sec_role (id, name, description, created_at, "
                "updated_at) VALUES (1, 'admin', '', CURRENT_TIMESTAMP, "
                "CURRENT_TIMESTAMP), (2, 'editor', '', CURRENT_TIMESTAMP, "
                "CURRENT_TIMESTAMP)"
            )
        )
        conn.execute(
            text("INSERT INTO sec_users_roles (user_id, role_id) VALUES (1, 1), (3, 2)")
        )
        conn.commit()
        yield conn
    engine.dispose()


def _roles(conn: Connection) -> dict[str, str]:
    rows = conn.execute(text("SELECT username, role FROM sec_user")).fetchall()
    return dict(rows)


def test_admins_stay_admins_and_everyone_else_becomes_deployer(old_server):
    _run(old_server, "upgrade")

    assert _roles(old_server) == {
        "alice": "admin",
        "bob": "deployer",
        "carol": "deployer",
    }


def test_the_old_role_tables_are_gone(old_server):
    _run(old_server, "upgrade")

    tables = set(inspect(old_server).get_table_names())
    assert "sec_role" not in tables
    assert "sec_users_roles" not in tables


def test_running_it_twice_changes_nothing(old_server):
    _run(old_server, "upgrade")
    old_server.execute(text("UPDATE sec_user SET role = 'viewer' WHERE id = 2"))

    _run(old_server, "upgrade")

    assert _roles(old_server)["bob"] == "viewer"


def test_downgrade_restores_the_admin_role_rows(old_server):
    _run(old_server, "upgrade")
    _run(old_server, "downgrade")

    admins = old_server.execute(
        text(
            "SELECT u.username FROM sec_user u "
            "JOIN sec_users_roles ur ON ur.user_id = u.id "
            "JOIN sec_role r ON r.id = ur.role_id WHERE r.name = 'admin'"
        )
    ).fetchall()
    assert [row[0] for row in admins] == ["alice"]
    assert "role" not in {
        c["name"] for c in inspect(old_server).get_columns("sec_user")
    }
