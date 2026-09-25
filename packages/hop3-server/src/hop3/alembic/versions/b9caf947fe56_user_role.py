# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
One standard role per account (ADR 061).

Adds ``sec_user.role`` and retires the free-form ``sec_role`` table and its
``sec_users_roles`` association. Only one role name was ever created there,
``admin``, so the mapping is exact: an account that held it becomes ``admin``.
Every other account becomes ``deployer``, which is what it could do before
roles were enforced: run and configure every app, without managing users
(ADR 061 §7). A new account created after this migration starts as ``member``.

Revision ID: b9caf947fe56
Revises: c9e4a1b7d2f3
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "b9caf947fe56"
down_revision: str | Sequence[str] | None = "c9e4a1b7d2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Wide enough for every role value, and what ``User.role`` declares.
_ROLE_LENGTH = 16


def _has_table(name: str) -> bool:
    """True if the live database already has table ``name``."""
    return name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table: str, column: str) -> bool:
    """True if the live database already has ``table.column``."""
    columns = sa.inspect(op.get_bind()).get_columns(table)
    return any(c["name"] == column for c in columns)


def upgrade() -> None:
    """
    Add the role column, carry the admin role over, drop the old tables.

    Idempotent: a brand-new database gets ``sec_user.role`` from ``create_all``
    and never had the old tables, so every step below is skipped when such a
    database is adopted.
    """
    if not _has_column("sec_user", "role"):
        with op.batch_alter_table("sec_user") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "role",
                    sa.String(length=_ROLE_LENGTH),
                    nullable=False,
                    server_default="member",
                )
            )

    if not (_has_table("sec_role") and _has_table("sec_users_roles")):
        return

    conn = op.get_bind()
    conn.execute(sa.text("UPDATE sec_user SET role = 'deployer'"))
    conn.execute(
        sa.text(
            "UPDATE sec_user SET role = 'admin' WHERE id IN ("
            "SELECT ur.user_id FROM sec_users_roles ur "
            "JOIN sec_role r ON r.id = ur.role_id WHERE r.name = 'admin')"
        )
    )
    op.drop_table("sec_users_roles")
    op.drop_table("sec_role")


def downgrade() -> None:
    """
    Recreate the old tables, with ``admin`` as their one role, and drop the column.

    ``deployer``, ``viewer`` and ``member`` have no equivalent in the old model,
    where every account could do everything; all three become plain accounts.
    """
    op.create_table(
        "sec_role",
        sa.Column(
            "id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sec_role")),
        sa.UniqueConstraint("name", name=op.f("uq_sec_role_name")),
    )
    op.create_table(
        "sec_users_roles",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["sec_user.id"],
            name=op.f("fk_sec_users_roles_user_id_sec_user"),
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["sec_role.id"],
            name=op.f("fk_sec_users_roles_role_id_sec_role"),
        ),
        sa.PrimaryKeyConstraint("user_id", "role_id", name=op.f("pk_sec_users_roles")),
    )
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO sec_role (name, description, created_at, updated_at) "
            "VALUES ('admin', 'Administrator role', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
    )
    conn.execute(
        sa.text(
            "INSERT INTO sec_users_roles (user_id, role_id) "
            "SELECT u.id, r.id FROM sec_user u, sec_role r "
            "WHERE u.role = 'admin' AND r.name = 'admin'"
        )
    )
    with op.batch_alter_table("sec_user") as batch_op:
        batch_op.drop_column("role")
