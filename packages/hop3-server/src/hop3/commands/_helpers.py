# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Shared helper functions for commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.orm import App
from hop3.orm.repositories import AppRepository

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def get_app(db_session: Session, app_name: str) -> App:
    """Retrieve an app by name or raise a consistent error.

    Args:
        db_session: Database session
        app_name: Name of the application

    Returns:
        The App object

    Raises:
        ValueError: If the app is not found
    """
    app_repo = AppRepository(session=db_session)
    app = app_repo.get_one_or_none(name=app_name)
    if not app:
        msg = f"App '{app_name}' not found."
        raise ValueError(msg)
    return app
