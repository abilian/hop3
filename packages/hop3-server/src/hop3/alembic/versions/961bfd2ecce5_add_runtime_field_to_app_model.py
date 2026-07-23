# Copyright (c) 2025, Abilian SAS
"""
add runtime field to app model

Revision ID: 961bfd2ecce5
Revises: 0d21c362f66d
Create Date: 2025-11-24 22:19:14.012460

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "961bfd2ecce5"
down_revision: str | Sequence[str] | None = "0d21c362f66d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _app_has_column(name: str) -> bool:
    """True if the live ``app`` table already has column ``name``."""
    bind = op.get_bind()
    return name in {col["name"] for col in sa.inspect(bind).get_columns("app")}


def upgrade() -> None:
    """
    Upgrade schema to add runtime field.

    Idempotent (see the error_message migration): skip when a create_all DB
    being adopted already has the column.
    """
    if _app_has_column("runtime"):
        return

    # Add runtime column with default value 'uwsgi' for existing apps
    op.add_column(
        "app",
        sa.Column(
            "runtime", sa.String(length=64), server_default="uwsgi", nullable=False
        ),
    )


def downgrade() -> None:
    """Downgrade schema to remove runtime field."""
    op.drop_column("app", "runtime")
