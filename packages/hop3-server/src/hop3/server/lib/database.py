# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Database utilities for the web server."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from hop3.orm import get_session_factory

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session


@contextmanager
def get_session() -> Iterator[Session]:
    """
    Get a database session as a context manager.

    Yields:
        Session: SQLAlchemy session
    """
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
