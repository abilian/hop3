# Copyright (c) 2019-2024, Abilian SAS - All rights reserved

from __future__ import annotations

from flask_security import SQLAlchemyUserDatastore
from hop3_main.models.auth import User
from sqlalchemy.orm import Query

# HACK: emulate flask-sqlalchemy's db.Model.query
# User.query = sqlalchemy.orm.query.Query(User)


# HACK
# (Avoids writing our own SQLAlchemyUserDatastore-like class)
class QueryProperty:
    # Adapted from flask-sqlalchemy (flask_sqlalchemy/model.py)

    def __get__(self, obj, cls) -> Query:
        from app.extensions import db

        return Query(cls, session=db.session())


# Monkey-patch to make it quack like a db.Model
User.query = QueryProperty()


def get_user_datastore():
    # Lazy import to prevent circular imports
    from app.extensions import db

    return SQLAlchemyUserDatastore(db, User, Role)
