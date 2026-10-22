# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
give port_claim, ban and network an auto-assigned id on SQLite

Their migrations created ``id BIGINT PRIMARY KEY``. On SQLite only an
``INTEGER PRIMARY KEY`` aliases the rowid and is assigned on insert, so every
insert into these tables failed with ``NOT NULL constraint failed: <table>.id``
on a server that had run those migrations (``hop3 addon expose``, an app's
``[[ports]]``). A fresh install, built by ``create_all``, was never affected.

Revision ID: e4b7c2a9f1d3
Revises: a7c3e9d51f20
Create Date: 2026-10-20 00:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "e4b7c2a9f1d3"
down_revision: str | Sequence[str] | None = "a7c3e9d51f20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("port_claim", "ban", "network")


def _id_type(table: str) -> str:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table)
    return next(str(c["type"]) for c in columns if c["name"] == "id")


def upgrade() -> None:
    """Rebuild each table whose id is not the rowid alias; the rows are kept."""
    if op.get_bind().dialect.name != "sqlite":
        return
    for table in TABLES:
        if _id_type(table) == "INTEGER":
            continue
        with op.batch_alter_table(table, recreate="always") as batch:
            batch.alter_column("id", existing_type=sa.BigInteger(), type_=sa.Integer())


def downgrade() -> None:
    """Nothing to undo: the BIGINT id was the bug, and the schema stays valid."""
