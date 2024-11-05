# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from hop3.model import metadata
from sqlalchemy import create_engine
from sqlalchemy_utils import create_database, database_exists

engine = create_engine("sqlite:///data/hop3.db")
if not database_exists(engine.url):
    create_database(engine.url)

metadata.create_all(engine)
