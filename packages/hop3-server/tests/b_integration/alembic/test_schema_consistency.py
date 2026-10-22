# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Schema-consistency guard: fresh-install schema must equal upgraded schema.

A Hop3 server can reach its schema by two paths that MUST converge:

  * fresh install  -> ``BigIntAuditBase.metadata.create_all()`` (orm/session.py
    bootstraps a brand-new DB this way, then stamps head);
  * upgraded server -> the create_all'd schema is adopted (stamp base) and
    ``alembic upgrade head`` applies the migrations.

If the two drift, a fresh-install box and an upgraded box run different
schemas — the exact class of bug found in the ``port_claim`` migration
(``BigInteger`` vs the ORM's id type, tz-aware timestamps, named PK/FK,
``server_default``). These tests build both schemas in two in-memory SQLite
DBs and compare them per table: column names + types + nullability, plus the
PK / FK / unique constraints.

Cross-dialect caveat: SQLite collapses ``BIGINT``/``SMALLINT`` to ``INTEGER``
affinity and renders ``DateTime(timezone=True)`` the same as a naive
``DateTime``. So a SQLite type-string match cannot *prove* Postgres parity for
those — but column SETS, names and nullability are compared exactly, which is
where real drift (a missing column, a wrong nullable) shows up. Type equality
is asserted at SQLite *affinity* granularity, the strongest claim this engine
can back.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from advanced_alchemy.base import BigIntAuditBase
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

import hop3
import hop3.orm  # ruff:ignore[unused-import]  -- populate BigIntAuditBase.metadata with all models

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.engine import Engine, Inspector

# Tables that are an artifact of the comparison, not part of the app schema.
_IGNORED_TABLES = {"alembic_version"}

# Tables a migration creates with its own DDL. Each needs nothing else's FK.
MIGRATION_CREATED_TABLES = ("port_claim", "ban", "network", "app_admin_credential")


def _sqlite_affinity(type_repr: str) -> str:
    """
    Map a rendered SQLite column type to its storage affinity.

    SQLite has only five affinities (INTEGER/TEXT/BLOB/REAL/NUMERIC) and maps
    every declared type onto one. BIGINT/SMALLINT/INT all share INTEGER
    affinity; VARCHAR(n)/TEXT/CHAR share TEXT. Comparing at this granularity
    is the right cross-dialect claim: it ignores SQLite's cosmetic
    INTEGER-vs-BIGINT rendering (identical on Postgres) while still catching a
    genuine family change (e.g. TEXT becoming INTEGER).
    """
    t = type_repr.upper()
    if "INT" in t:
        return "INTEGER"
    if any(token in t for token in ("CHAR", "CLOB", "TEXT")):
        return "TEXT"
    if "BLOB" in t or t == "":
        return "BLOB"
    if any(token in t for token in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    return "NUMERIC"  # DATETIME, BOOLEAN, NUMERIC, etc.


def _columns(inspector: Inspector, table: str) -> dict[str, tuple[str, bool]]:
    """{column_name: (affinity, nullable)} for a table — the comparable shape."""
    return {
        col["name"]: (_sqlite_affinity(str(col["type"])), bool(col["nullable"]))
        for col in inspector.get_columns(table)
    }


def _primary_key(inspector: Inspector, table: str) -> frozenset[str]:
    return frozenset(inspector.get_pk_constraint(table)["constrained_columns"])


def _foreign_keys(
    inspector: Inspector, table: str
) -> frozenset[tuple[tuple[str, ...], str, tuple[str, ...]]]:
    """
    Set of (local_cols, referred_table, referred_cols) for a table.

    Order-independent so a reordering of FK declarations never trips the guard.
    """
    return frozenset(
        (
            tuple(fk["constrained_columns"]),
            fk["referred_table"],
            tuple(fk["referred_columns"]),
        )
        for fk in inspector.get_foreign_keys(table)
    )


def _unique_constraints(inspector: Inspector, table: str) -> frozenset[tuple[str, ...]]:
    """Set of unique-constraint column tuples (sorted within each tuple)."""
    return frozenset(
        tuple(sorted(uc["column_names"]))
        for uc in inspector.get_unique_constraints(table)
    )


def _user_tables(inspector: Inspector) -> set[str]:
    return set(inspector.get_table_names()) - _IGNORED_TABLES


def _alembic_config(connection) -> Config:
    """
    Programmatic Alembic config bound to an open connection.

    Mirrors how orm/session.py and server/cli/db.py locate the bundled
    alembic.ini (from the hop3 package root, so it works installed or editable).
    """
    ini_path = Path(hop3.__file__).parent / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.attributes["connection"] = connection
    return cfg


@pytest.fixture
def create_all_engine() -> Iterator[Engine]:
    """Fresh-install schema: a pure ``metadata.create_all`` in-memory DB."""
    engine = create_engine("sqlite:///:memory:")
    BigIntAuditBase.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def migrated_engine() -> Iterator[Engine]:
    """
    Upgraded-server schema via the real adoption flow.

    Reproduces what a deployed server actually does: a create_all'd schema is
    adopted (stamp the base revision) and then ``upgrade head`` runs. The delta
    migrations are idempotent, so this lands the schema at head exactly as a
    migrated server would. The tables a migration creates are dropped first so
    each migration's own ``op.create_table`` runs for real: that hand-written
    DDL must match the ORM, and is where the drift bugs lived.
    """
    engine = create_engine("sqlite:///:memory:")
    BigIntAuditBase.metadata.create_all(engine)
    with engine.connect() as conn:
        for table in MIGRATION_CREATED_TABLES:
            conn.exec_driver_sql(f"DROP TABLE {table}")
        cfg = _alembic_config(conn)
        base = ScriptDirectory.from_config(cfg).get_bases()[0]
        command.stamp(cfg, base)
        command.upgrade(cfg, "head")
        conn.commit()
    yield engine
    engine.dispose()


def test_same_table_set(create_all_engine: Engine, migrated_engine: Engine) -> None:
    """Both paths must expose the same set of application tables."""
    fresh = _user_tables(inspect(create_all_engine))
    upgraded = _user_tables(inspect(migrated_engine))

    assert fresh == upgraded


def test_columns_match_per_table(
    create_all_engine: Engine, migrated_engine: Engine
) -> None:
    """
    Every table has identical columns: names, type affinity, nullability.

    Robust to future tables: it iterates whatever tables the schema defines,
    so adding a model (or migration) is covered automatically — and a column
    that exists on only one path, or whose nullability/affinity diverges,
    fails here. This is the guard the port_claim drift would have tripped.
    """
    fresh_insp = inspect(create_all_engine)
    upgraded_insp = inspect(migrated_engine)

    for table in sorted(_user_tables(fresh_insp)):
        assert _columns(fresh_insp, table) == _columns(upgraded_insp, table), (
            f"column drift in table {table!r}"
        )


def test_constraints_match_per_table(
    create_all_engine: Engine, migrated_engine: Engine
) -> None:
    """
    PK, FK and unique constraints must match per table across both paths.

    Unnamed/mismatched PKs and FKs were part of the port_claim incident; this
    locks the constraint shape (including the FK's referred table/columns and
    each unique-constraint column set) so a migration can't silently differ.
    """
    fresh_insp = inspect(create_all_engine)
    upgraded_insp = inspect(migrated_engine)

    for table in sorted(_user_tables(fresh_insp)):
        assert _primary_key(fresh_insp, table) == _primary_key(upgraded_insp, table), (
            f"primary-key drift in table {table!r}"
        )
        assert _foreign_keys(fresh_insp, table) == _foreign_keys(
            upgraded_insp, table
        ), f"foreign-key drift in table {table!r}"
        assert _unique_constraints(fresh_insp, table) == _unique_constraints(
            upgraded_insp, table
        ), f"unique-constraint drift in table {table!r}"


def test_port_claim_is_actually_built_by_migration(migrated_engine: Engine) -> None:
    """
    Guard the guard: the migration really created port_claim (not create_all).

    The migrated fixture drops port_claim before upgrading so the migration's
    hand-written ``op.create_table`` is the thing under test. If that DDL ever
    stopped running (e.g. the idempotency guard misfired), the comparison tests
    would silently pass against a create_all'd table and prove nothing. This
    asserts the table is present with its key columns after the migration path.
    """
    insp = inspect(migrated_engine)

    columns = set(_columns(insp, "port_claim"))

    assert {"id", "app_id", "number", "protocol", "app_name"} <= columns


def test_primary_keys_match_exactly(
    create_all_engine: Engine, migrated_engine: Engine
) -> None:
    """
    The id column's declared type matches, beyond its affinity.

    On SQLite only ``INTEGER PRIMARY KEY`` aliases the rowid and is assigned on
    insert; ``BIGINT PRIMARY KEY`` has the same affinity and is not. Three
    migrations created ``BIGINT`` ids, and every insert into those tables
    failed on a migrated server, which ``hop3 addon expose`` reported as a port
    taken by a concurrent operation.
    """
    fresh_insp = inspect(create_all_engine)
    upgraded_insp = inspect(migrated_engine)

    for table in sorted(_user_tables(fresh_insp)):
        for column in _primary_key(fresh_insp, table):
            assert _declared_type(fresh_insp, table, column) == _declared_type(
                upgraded_insp, table, column
            ), f"primary-key type drift in {table}.{column}"


def test_a_server_migrated_with_bigint_ids_gets_them_repaired(
    migrated_engine: Engine,
) -> None:
    """The repair rebuilds each broken table, keeps its rows, and inserts work."""
    with migrated_engine.connect() as conn:
        for table in ("port_claim", "ban", "network"):
            ddl = conn.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE name = ?", (table,)
            ).scalar_one()
            conn.exec_driver_sql(f"DROP TABLE {table}")
            conn.exec_driver_sql(ddl.replace("id INTEGER", "id BIGINT", 1))
        conn.exec_driver_sql(
            "INSERT INTO port_claim (id, created_at, updated_at, number, protocol,"
            " app_name, source) VALUES (7, 'now', 'now', 28303, 'tcp', 'kept', 'any')"
        )
        cfg = _alembic_config(conn)
        command.stamp(cfg, "a7c3e9d51f20")
        command.upgrade(cfg, "head")
        conn.exec_driver_sql(
            "INSERT INTO port_claim (created_at, updated_at, number, protocol,"
            " app_name, source) VALUES ('now', 'now', 24591, 'tcp', 'new', 'any')"
        )
        rows = conn.exec_driver_sql(
            "SELECT id, app_name FROM port_claim ORDER BY id"
        ).all()
        insp = inspect(conn)
        types = {t: _declared_type(insp, t, "id") for t in ("ban", "network")}

    assert [tuple(row) for row in rows] == [(7, "kept"), (8, "new")]
    assert types == {"ban": "INTEGER", "network": "INTEGER"}


def _declared_type(inspector: Inspector, table: str, column: str) -> str:
    return next(
        str(c["type"]) for c in inspector.get_columns(table) if c["name"] == column
    )
