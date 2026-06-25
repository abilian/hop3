# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Test Lab-owned tables: build profiles, the server pool, and the build queue.

The Lab is otherwise a read-client of the shared hop3-testing result store; these
are the few tables it *owns* and writes. They live in the **same** database (one
store) under a separate declarative ``Base`` and a ``testlab_`` table prefix, so
they never collide with the engine's result schema. The schema is created by
``db.get_session_factory`` via ``Base.metadata.create_all`` (dialect-aware, so the
Postgres backend is free).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for the Lab's own tables (distinct from the engine's)."""


def _utcnow() -> datetime:
    return datetime.now(UTC)


# BuildRequest lifecycle — a plain string column (no enum table needed).
QUEUED = "pending"
DISPATCHED = "dispatched"
RUNNING = "running"
DONE = "done"
CANCELLED = "cancelled"
FAILED = "failed"


class Profile(Base):
    """A saved build spec — *what* to build (source@ref + platform ref + rules)."""

    __tablename__ = "testlab_profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    source_name: Mapped[str] = mapped_column(String(120))
    source_url: Mapped[str] = mapped_column(String(500))
    source_ref: Mapped[str] = mapped_column(String(200))
    # None -> the engine's default platform branch.
    platform_ref: Mapped[str | None] = mapped_column(String(200), default=None)
    # Rule-based selection (ModeConfig-shaped); never a manual app list.
    selection: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class Server(Base):
    """A pool entry — *where* a build can run. The dispatcher picks a free one.

    ``target_id`` is what ``worker.run_once`` already takes (``docker`` | an SSH
    host | ``hetzner``); credentials stay in config, never in this row.
    """

    __tablename__ = "testlab_server"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    target_id: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(40))  # docker | ssh | hetzner
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class Credential(Base):
    """A cloud-provider credential the worker uses to reach run targets.

    Secrets (``api_token``, ``private_key``) live here in the DB like other
    app-level secrets — redacted wherever displayed. ``load_cloud_config``
    resolves the active credential of a ``kind`` and materializes ``private_key``
    to a 0600 file for the engine subprocess. Several providers/accounts = several
    rows; a ``Server`` row will pick a specific one in a later slice.
    """

    __tablename__ = "testlab_credential"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(40))  # hetzner | ...
    api_token: Mapped[str] = mapped_column(Text)
    server_id: Mapped[int | None] = mapped_column(Integer, default=None)
    image: Mapped[str] = mapped_column(String(120), default="ubuntu-24.04")
    ssh_key_name: Mapped[str | None] = mapped_column(String(200), default=None)
    private_key: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class BuildRequest(Base):
    """A queued build. Start-build enqueues one (no target); the dispatcher
    assigns a free pool server and records the resulting run."""

    __tablename__ = "testlab_build_request"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("testlab_profile.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default=QUEUED, index=True)
    server_target_id: Mapped[str | None] = mapped_column(String(200), default=None)
    run_uid: Mapped[str | None] = mapped_column(String(120), default=None)
    actor: Mapped[str | None] = mapped_column(String(120), default=None)
    # Failure reason / breadcrumb — fail loud, never silently drop a request.
    # Text, not String(500): a real deploy/crash reason runs to many lines and was
    # being truncated mid-error (and once overflowed varchar(500), crashing the
    # recorder). Existing Postgres deploys are widened by db._widen_build_detail.
    detail: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
