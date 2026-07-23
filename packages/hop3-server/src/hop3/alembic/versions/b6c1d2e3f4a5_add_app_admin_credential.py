# Copyright (c) 2026, Abilian SAS
"""
add app_admin_credential table (ADR 056 — bootstrapped app admin creds)

Revision ID: b6c1d2e3f4a5
Revises: a7b8c9d0e1f2
Create Date: 2026-07-17 00:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "b6c1d2e3f4a5"
down_revision: str | Sequence[str] | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(name: str) -> bool:
    """True if the live database already has table ``name``."""
    bind = op.get_bind()
    return name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    """
    Create the app_admin_credential table (ADR 056).

    Idempotent: a fresh database gets all tables via ``create_all`` (then
    stamped at head), so this guard skips the create when such a DB is adopted.
    Column types + constraint names match BigIntAuditBase's create_all output so
    a migrated server and a fresh-install server get an identical schema.
    """
    if _has_table("app_admin_credential"):
        return
    op.create_table(
        "app_admin_credential",
        # BigInteger everywhere EXCEPT the SQLite variant, which must be INTEGER
        # so the PK aliases rowid and auto-increments — matching what
        # BigIntAuditBase's create_all emits, so a migrated DB == a fresh one.
        # A plain BIGINT PK on SQLite does NOT auto-increment (insert fails on a
        # NULL id).
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("app_id", sa.BigInteger(), nullable=False),
        sa.Column("encrypted_data", sa.String(length=2048), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("bootstrapped", sa.Boolean(), nullable=False),
        sa.Column("surfaced", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["app_id"],
            ["app.id"],
            name="fk_app_admin_credential_app_id_app",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_app_admin_credential"),
        sa.UniqueConstraint("app_id", name="uq_app_admin_credential_app"),
    )


def downgrade() -> None:
    if _has_table("app_admin_credential"):
        op.drop_table("app_admin_credential")
