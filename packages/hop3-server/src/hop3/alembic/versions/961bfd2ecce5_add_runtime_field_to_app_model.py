# Copyright (c) 2025, Abilian SAS
"""add runtime field to app model

Revision ID: 961bfd2ecce5
Revises: 0d21c362f66d
Create Date: 2025-11-24 22:19:14.012460

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "961bfd2ecce5"
down_revision: str | Sequence[str] | None = "0d21c362f66d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema to add runtime field."""
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
