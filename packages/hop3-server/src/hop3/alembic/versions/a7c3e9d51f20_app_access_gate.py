# Copyright (c) 2026, Abilian SAS
"""
add the access gate columns to app (ADR 062)

Revision ID: a7c3e9d51f20
Revises: b9caf947fe56
Create Date: 2026-09-25 00:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "a7c3e9d51f20"
down_revision: str | Sequence[str] | None = "b9caf947fe56"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = (
    sa.Column("access_role", sa.String(16), nullable=True),
    sa.Column("access_public_paths", sa.JSON(), nullable=False, server_default="[]"),
)


def _has_column(table: str, column: str) -> bool:
    """True if the live database already has ``table.column``."""
    bind = op.get_bind()
    return any(c["name"] == column for c in sa.inspect(bind).get_columns(table))


def upgrade() -> None:
    """
    Add app.access_role and app.access_public_paths.

    Idempotent: a new database gets the columns from ``create_all`` and is then
    stamped at head. Existing apps get no gate (NULL), as before this column.
    """
    for column in COLUMNS:
        if not _has_column("app", column.name):
            op.add_column("app", column.copy())


def downgrade() -> None:
    for column in COLUMNS:
        if _has_column("app", column.name):
            op.drop_column("app", column.name)
