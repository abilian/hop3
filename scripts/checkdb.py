# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from sqlalchemy import create_engine
from sqlalchemy_utils import database_exists, create_database

from hop3.model import metadata

engine = create_engine("sqlite:///data/hop3.db")
if not database_exists(engine.url):
    create_database(engine.url)

metadata.create_all(engine)
