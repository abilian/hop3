# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""The is_primary migration backfills one primary per (app_id, addon_type).

The winner is the most-recently-attached row (max id), preserving whatever
``DATABASE_URL`` resolves to under the pre-migration "last attach overwrites"
behaviour.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op
from sqlalchemy import create_engine, text

import hop3


def _load_migration():
    path = (
        Path(hop3.__file__).parent
        / "alembic"
        / "versions"
        / "d8b3f1a6c2e4_addon_credential_is_primary.py"
    )
    spec = importlib.util.spec_from_file_location("mig_is_primary", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_backfill_picks_max_id_per_group(monkeypatch):
    migration = _load_migration()
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE addon_credential "
            "(id INTEGER PRIMARY KEY, app_id INTEGER, addon_type TEXT, "
            "is_primary INTEGER DEFAULT 0)"
        )
        conn.exec_driver_sql(
            "INSERT INTO addon_credential (id, app_id, addon_type, is_primary) VALUES "
            "(1, 1, 'postgres', 0), (2, 1, 'postgres', 0), "
            "(3, 1, 'redis', 0), (4, 2, 'postgres', 0)"
        )

    conn = engine.connect()
    monkeypatch.setattr(op, "get_bind", lambda: conn)
    migration._backfill_primaries()
    conn.commit()

    rows = dict(
        conn.execute(text("SELECT id, is_primary FROM addon_credential")).fetchall()
    )
    conn.close()
    engine.dispose()

    # Winners (max id per (app_id, addon_type)): (1,pg)->2, (1,redis)->3, (2,pg)->4.
    assert rows[2] == 1
    assert rows[3] == 1
    assert rows[4] == 1
    assert rows[1] == 0  # the older postgres of app 1 is not primary
