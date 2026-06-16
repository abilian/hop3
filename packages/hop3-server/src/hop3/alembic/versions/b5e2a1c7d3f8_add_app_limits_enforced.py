# Copyright (c) 2026, Abilian SAS
"""add limits_enforced / limits_detail to the app model

Records the resolved [limits] enforcement outcome (ADR 046 §3 / P2.2) so
`hop3 app status` can show the applied caps or the why-unenforced reason.

Revision ID: b5e2a1c7d3f8
Revises: a3f1c9e2b4d6
Create Date: 2026-06-16 00:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "b5e2a1c7d3f8"
down_revision: str | Sequence[str] | None = "a3f1c9e2b4d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    """True if the live database already has ``table.column``."""
    bind = op.get_bind()
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    """Add the two columns.

    Idempotent: a brand-new database gets them via ``create_all`` (then stamped
    at head), so the guards skip the add when such a DB is adopted. A
    ``server_default`` of "" backfills existing rows for the NOT NULL columns
    (the model's Python-side default keeps new rows consistent on both paths).
    """
    if not _has_column("app", "limits_enforced"):
        op.add_column(
            "app",
            sa.Column(
                "limits_enforced",
                sa.String(length=16),
                nullable=False,
                server_default="",
            ),
        )
    if not _has_column("app", "limits_detail"):
        op.add_column(
            "app",
            sa.Column(
                "limits_detail",
                sa.String(length=512),
                nullable=False,
                server_default="",
            ),
        )


def downgrade() -> None:
    """Drop the two columns."""
    if _has_column("app", "limits_detail"):
        op.drop_column("app", "limits_detail")
    if _has_column("app", "limits_enforced"):
        op.drop_column("app", "limits_enforced")
