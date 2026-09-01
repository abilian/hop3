# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Data models for Hop3 API responses."""

from __future__ import annotations

from datetime import (
    datetime,
)
from enum import Enum

from pydantic import BaseModel


class AppState(str, Enum):
    """Application state enumeration.

    ``CRASHED`` is not a stored state: `app status` reports it when the database
    says RUNNING and no process answers. The client had no member for it, so
    reading a crashed app raised ValueError out of a render.
    """

    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    FAILED = "FAILED"
    CRASHED = "CRASHED"


class EnvVar(BaseModel):
    """Environment variable model."""

    name: str
    value: str
    is_service_var: bool = False


class App(BaseModel):
    """Application model."""

    name: str
    runtime: str = "unknown"
    state: AppState = AppState.STOPPED
    port: int | None = None
    hostname: str | None = None
    workers: int = 1
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def is_running(self) -> bool:
        return self.state == AppState.RUNNING

    @property
    def is_transitional(self) -> bool:
        return self.state in {AppState.STARTING, AppState.STOPPING}


class SystemStatus(BaseModel):
    """System status model."""

    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    disk_percent: float = 0.0
    uptime_seconds: int = 0
    hostname: str = "unknown"
    hop3_version: str = "unknown"
    apps_running: int = 0
    apps_stopped: int = 0
    apps_failed: int = 0


class Addon(BaseModel):
    """Addon model."""

    name: str
    addon_type: str
    app_name: str | None = None
    created_at: datetime | None = None


class Backup(BaseModel):
    """One row of `backup list`, as the server renders it.

    The size and the timestamp arrive already formatted for reading, so they are
    kept as text. Modelling them as ``size_bytes: int`` meant the screen read a
    field the wire never fills, and every row's size column showed a dash.
    """

    id: str
    app_name: str
    size: str = "-"
    created: str = "-"
    state: str = ""
    addons: str = "-"
