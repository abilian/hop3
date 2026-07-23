# Copyright (c) 2026, Abilian SAS
"""
add is_primary to addon_credential (per-addon env namespacing)

When >1 addon of a type is attached to an app, the primary injects the
unprefixed connection vars (DATABASE_URL, …); others are prefixed. Adds the
flag and backfills exactly one primary per (app_id, addon_type).

Revision ID: d8b3f1a6c2e4
Revises: c7d4e8f1a2b9
Create Date: 2026-06-16 00:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "d8b3f1a6c2e4"
down_revision: str | Sequence[str] | None = "c7d4e8f1a2b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    """True if the live database's ``table`` already has ``column``."""
    bind = op.get_bind()
    return any(c["name"] == column for c in sa.inspect(bind).get_columns(table))


def _backfill_primaries() -> None:
    """
    Mark one primary per (app_id, addon_type) group.

    Picks the most-recently-attached row (max id) so the value `DATABASE_URL`
    currently resolves to is preserved across the upgrade — under the old
    "last attach overwrites" behaviour, the newest credential is what the app
    sees today. (Detach's auto-promotion deliberately uses the *oldest* sibling
    instead — that's about stability of the remaining set, not preserving a
    current value.)
    """
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, app_id, addon_type FROM addon_credential ORDER BY id")
    ).fetchall()
    winners: dict[tuple[object, object], object] = {}
    for row in rows:
        cred_id, app_id, addon_type = row[0], row[1], row[2]
        winners[app_id, addon_type] = cred_id  # ordered by id → last wins = max id
    for cred_id in winners.values():
        bind.execute(
            sa.text("UPDATE addon_credential SET is_primary = 1 WHERE id = :id"),
            {"id": cred_id},
        )


def upgrade() -> None:
    """
    Add is_primary (native ADD COLUMN; SQLite-safe) + backfill.

    Idempotent: a fresh-install DB already has the column via ``create_all``
    (and no rows to backfill), so the guard skips when it's present.
    """
    if _has_column("addon_credential", "is_primary"):
        return
    op.add_column(
        "addon_credential",
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="0"),
    )
    _backfill_primaries()


def downgrade() -> None:
    """Drop the is_primary column."""
    if _has_column("addon_credential", "is_primary"):
        op.drop_column("addon_credential", "is_primary")
