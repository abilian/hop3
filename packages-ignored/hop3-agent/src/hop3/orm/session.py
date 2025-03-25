# Copyright (c) 2024-2025, Abilian SAS
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from hop3 import config as c

from .app import App


def get_session_factory(database_uri: str = "") -> sessionmaker:
    if not database_uri:
        database_uri = f"sqlite:///{c.HOP3_ROOT}/hop3.db"

    engine = create_engine(database_uri)

    with engine.begin() as conn:
        App.metadata.create_all(conn)

    return sessionmaker(bind=engine)
