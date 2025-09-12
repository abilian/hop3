# Copyright (c) 2024-2025, Abilian SAS
from __future__ import annotations

from advanced_alchemy.repository import ModelT, SQLAlchemySyncRepository

from .app import App


class BaseRepository(SQLAlchemySyncRepository[ModelT]):
    """Base class for repositories."""


class AppRepository(BaseRepository[App]):
    """Repository for managing App entities."""

    model_type = App
