# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Make app.name unique, and app.image_tag NOT NULL.

The app name is the identity used by every lookup and by the on-disk path
(``APP_ROOT / name``), but nothing enforced it. Two rows sharing a name are
insertable, and from then on every ``get_app_or_none()`` raises
``MultipleResultsFound``: the app becomes unreachable from both the CLI and
the dashboard, and the only visible symptom is a 500.

If duplicates already exist this migration **aborts with the offending
names** rather than guessing which row to delete. Picking one would silently
discard an app's env vars, addon credentials and port claims; that is the
operator's call, not the migration's.

Revision ID: c9e4a1b7d2f3
Revises: b6c1d2e3f4a5
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "c9e4a1b7d2f3"
down_revision: str | Sequence[str] | None = "b6c1d2e3f4a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()

    duplicates = conn.execute(
        sa.text("SELECT name, COUNT(*) AS n FROM app GROUP BY name HAVING COUNT(*) > 1")
    ).fetchall()
    if duplicates:
        listed = ", ".join(f"{row[0]!r} ({row[1]} rows)" for row in duplicates)
        msg = (
            f"Cannot make app.name unique: duplicate app names already exist — "
            f"{listed}. Each duplicate owns its own env vars, addon credentials "
            f"and port claims, so this migration will not choose one to delete. "
            f"Remove the unwanted rows (`hop3 app destroy <name>` keeps the "
            f"remaining one consistent), then re-run the migration."
        )
        raise RuntimeError(msg)

    # Backfill before tightening: the column was nullable, so existing rows
    # may hold NULL and the NOT NULL would otherwise fail mid-migration.
    conn.execute(sa.text("UPDATE app SET image_tag = '' WHERE image_tag IS NULL"))

    # SQLite cannot ALTER a column or add a constraint in place; batch mode
    # rebuilds the table. It is a no-op wrapper on PostgreSQL/MySQL.
    with op.batch_alter_table("app") as batch_op:
        batch_op.alter_column(
            "image_tag",
            existing_type=sa.String(256),
            nullable=False,
            server_default="",
        )
        batch_op.create_unique_constraint("uq_app_name", ["name"])


def downgrade() -> None:
    with op.batch_alter_table("app") as batch_op:
        batch_op.drop_constraint("uq_app_name", type_="unique")
        batch_op.alter_column("image_tag", existing_type=sa.String(256), nullable=True)
