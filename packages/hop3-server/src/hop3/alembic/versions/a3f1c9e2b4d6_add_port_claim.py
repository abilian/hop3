# Copyright (c) 2026, Abilian SAS
"""add port_claim table for the fixed-port registry

Revision ID: a3f1c9e2b4d6
Revises: 961bfd2ecce5
Create Date: 2026-06-10 00:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "a3f1c9e2b4d6"
down_revision: str | Sequence[str] | None = "961bfd2ecce5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(name: str) -> bool:
    """True if the live database already has table ``name``."""
    bind = op.get_bind()
    return name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    """Create the port_claim table.

    Idempotent: a brand-new database gets all tables via ``create_all`` (then
    stamped at head), so this guard skips the create when such a DB is adopted.
    """
    if _has_table("port_claim"):
        return
    # Column types + constraint names match what BigIntAuditBase's create_all
    # produces (tz-aware timestamps; convention-named PK/FK), so a migrated
    # server and a fresh-install (create_all) server get an identical schema.
    op.create_table(
        "port_claim",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("app_id", sa.BigInteger(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("protocol", sa.String(length=3), nullable=False),
        sa.Column("app_name", sa.String(length=128), nullable=False),
        sa.Column("rule_id", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["app_id"], ["app.id"], name="fk_port_claim_app_id_app", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_port_claim"),
        sa.UniqueConstraint("number", "protocol", name="uq_port_claim_number_protocol"),
    )


def downgrade() -> None:
    """Drop the port_claim table."""
    if _has_table("port_claim"):
        op.drop_table("port_claim")
