# Copyright (c) 2026, Abilian SAS
"""
extend port_claim for addon exposure (hop3 addon expose)

Make ``app_id`` nullable (an exposed addon is not owned by an App) and add the
addon-exposure columns (addon_type / addon_name / proxy_unit / source).

Revision ID: c7d4e8f1a2b9
Revises: b5e2a1c7d3f8
Create Date: 2026-06-16 00:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "c7d4e8f1a2b9"
down_revision: str | Sequence[str] | None = "b5e2a1c7d3f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    """True if the live database's ``table`` already has ``column``."""
    bind = op.get_bind()
    return any(c["name"] == column for c in sa.inspect(bind).get_columns(table))


def upgrade() -> None:
    """
    Relax app_id + add the addon-exposure columns.

    Idempotent: a brand-new database gets the current schema via ``create_all``
    (then stamped at head), so this guard skips when the columns already exist.
    Batch mode is used because SQLite (the default backend) cannot ALTER a
    column's nullability in place.
    """
    if _has_column("port_claim", "addon_type"):
        return
    with op.batch_alter_table("port_claim") as batch:
        batch.alter_column("app_id", existing_type=sa.BigInteger(), nullable=True)
        batch.add_column(sa.Column("addon_type", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("addon_name", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("proxy_unit", sa.String(length=128), nullable=True))
        batch.add_column(
            sa.Column(
                "source", sa.String(length=64), nullable=False, server_default="any"
            )
        )


def downgrade() -> None:
    """Drop the addon-exposure columns and restore app_id NOT NULL."""
    if not _has_column("port_claim", "addon_type"):
        return
    with op.batch_alter_table("port_claim") as batch:
        batch.drop_column("source")
        batch.drop_column("proxy_unit")
        batch.drop_column("addon_name")
        batch.drop_column("addon_type")
        batch.alter_column("app_id", existing_type=sa.BigInteger(), nullable=False)
