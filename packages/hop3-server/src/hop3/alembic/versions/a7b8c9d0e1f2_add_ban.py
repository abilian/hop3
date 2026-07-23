# Copyright (c) 2026, Abilian SAS
"""
add ban table (ADR 050 §4 — per-app L7 WAF bans)

Revision ID: a7b8c9d0e1f2
Revises: f2a3b4c5d6e7
Create Date: 2026-06-25 00:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: str | Sequence[str] | None = "f2a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(name: str) -> bool:
    """True if the live database already has table ``name``."""
    bind = op.get_bind()
    return name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    """
    Create the ban table (ADR 050 §4 — per-app, time-limited source denials).

    Idempotent: a brand-new database gets all tables via ``create_all`` (then
    stamped at head), so this guard skips the create when such a DB is adopted.
    Column types + constraint names match BigIntAuditBase's create_all output so
    a migrated server and a fresh-install server get an identical schema.
    """
    if _has_table("ban"):
        return
    op.create_table(
        "ban",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("app_id", sa.BigInteger(), nullable=False),
        sa.Column("app_name", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=256), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["app_id"], ["app.id"], name="fk_ban_app_id_app", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ban"),
        sa.UniqueConstraint("app_id", "source", name="uq_ban_app_source"),
    )


def downgrade() -> None:
    if _has_table("ban"):
        op.drop_table("ban")
