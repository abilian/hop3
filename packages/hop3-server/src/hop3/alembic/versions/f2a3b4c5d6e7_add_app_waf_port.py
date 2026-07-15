# Copyright (c) 2026, Abilian SAS
"""add waf_port column to app (ADR 050 — per-app LeWAF proxy port)

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-06-24 00:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "f2a3b4c5d6e7"
down_revision: str | Sequence[str] | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    """True if the live database already has ``table.column``."""
    bind = op.get_bind()
    return any(c["name"] == column for c in sa.inspect(bind).get_columns(table))


def upgrade() -> None:
    """Add app.waf_port.

    Idempotent: a brand-new database gets the column via ``create_all`` (then
    stamped at head), so this guard skips the add when such a DB is adopted.
    Existing rows default to 0 — no WAF proxy, the behaviour before this column.
    """
    if _has_column("app", "waf_port"):
        return
    op.add_column(
        "app",
        sa.Column("waf_port", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    if _has_column("app", "waf_port"):
        op.drop_column("app", "waf_port")
