# Copyright (c) 2026, Abilian SAS
"""add source column to port_claim (per-port CIDR scoping)

Revision ID: c7d4e9f1a2b3
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
revision: str = "c7d4e9f1a2b3"
down_revision: str | Sequence[str] | None = "b5e2a1c7d3f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    """True if the live database already has ``table.column``."""
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns(table)}
    return column in cols


def upgrade() -> None:
    """Add port_claim.source.

    Idempotent: a brand-new database gets the column via ``create_all`` (then
    stamped at head), so this guard skips the add when such a DB is adopted.
    Existing rows default to "any" — the behaviour before this column existed
    (a declared port was opened to the whole internet).
    """
    if _has_column("port_claim", "source"):
        return
    op.add_column(
        "port_claim",
        sa.Column(
            "source",
            sa.String(length=64),
            nullable=False,
            server_default="any",
        ),
    )


def downgrade() -> None:
    if _has_column("port_claim", "source"):
        op.drop_column("port_claim", "source")
