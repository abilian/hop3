# Copyright (c) 2026, Abilian SAS
"""add network table (named CIDR sets for WAF gates)

Revision ID: e1f2a3b4c5d6
Revises: c7d4e9f1a2b3
Create Date: 2026-06-16 00:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: str | Sequence[str] | None = "c7d4e9f1a2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(name: str) -> bool:
    """True if the live database already has table ``name``."""
    bind = op.get_bind()
    return name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    """Create the network table (ADR 048 §2 — named CIDR sets for WAF gates).

    Idempotent: a brand-new database gets all tables via ``create_all`` (then
    stamped at head), so this guard skips the create when such a DB is adopted.
    Column types + constraint names match BigIntAuditBase's create_all output so
    a migrated server and a fresh-install server get an identical schema.
    """
    if _has_table("network"):
        return
    op.create_table(
        "network",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("cidrs", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_network"),
        sa.UniqueConstraint("name", name="uq_network_name"),
    )


def downgrade() -> None:
    if _has_table("network"):
        op.drop_table("network")
