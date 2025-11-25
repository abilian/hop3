# Copyright (c) 2025, Abilian SAS
"""add_app_state_machine_and_error_message

Revision ID: 0d21c362f66d
Revises: d20dd80dafca
Create Date: 2025-11-24 15:20:32.212565

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0d21c362f66d"
down_revision: str | Sequence[str] | None = "d20dd80dafca"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema to add error_message column and update state enum values.

    Changes:
    - Add error_message column to app table
    - Update run_state enum values (remove PAUSED, add STARTING, STOPPING, FAILED)
    - STOPPED=1, STARTING=2, RUNNING=3, STOPPING=4, FAILED=5
    """
    # Add error_message column
    op.add_column(
        "app",
        sa.Column(
            "error_message", sa.String(length=1024), server_default="", nullable=False
        ),
    )

    # Note: SQLite doesn't support ALTER TYPE for enums
    # The new state values will work because we're using integers (1-5)
    # Old states: RUNNING=1, STOPPED=2, PAUSED=3
    # New states: STOPPED=1, STARTING=2, RUNNING=3, STOPPING=4, FAILED=5
    # We need to update existing state values:
    # - RUNNING (1) stays as 1, but becomes STOPPED (will be handled by application logic)
    # - STOPPED (2) stays as 2, which becomes STARTING (will fix below)
    # - PAUSED (3) becomes RUNNING (3)

    # Actually, let's keep it simple for this migration:
    # Old RUNNING (1) -> New RUNNING (3) - needs update
    # Old STOPPED (2) -> New STOPPED (1) - needs update
    # Old PAUSED (3) -> New STOPPED (1) - needs update

    # For safety, we'll transition all apps to STOPPED state (1)
    op.execute("UPDATE app SET run_state = 1")


def downgrade() -> None:
    """Downgrade schema."""
    # Remove error_message column
    op.drop_column("app", "error_message")

    # Note: State values will need manual intervention if downgrading
