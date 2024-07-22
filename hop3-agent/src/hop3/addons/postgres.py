# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from dataclasses import dataclass

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from hop3.addons.base import Addon


@dataclass(frozen=True)
class PostgresqlAddon(Addon):
    app_name: str
    settings: dict

    def create(self) -> None:
        # Create the database
        params = {
            # 'dbname': self.db_name,
            "user": self.settings["pg_user"],
            "password": self.settings["pg_pw"],
            "host": "localhost",
            "port": 5432,
        }

        connection = psycopg2.connect(**params)
        connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        with connection.cursor() as cursor:
            if self._check_database_exists(cursor):
                return
            self._create_database(cursor)
        connection.close()

    @property
    def db_name(self) -> str:
        return self.app_name + "_db"

    @property
    def db_user(self) -> str:
        return self.app_name + "_user"

    @property
    def db_pass(self) -> str:
        return self.app_name + "_pw"

    def get_env(self) -> dict[str, str]:
        return {
            "DATABASE_URL": (
                f"postgresql://{self.db_user}:{self.db_pass}@localhost/{self.db_name}"
            ),
        }

    def _check_database_exists(self, cursor) -> bool:
        dbname = self.db_name
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
        exists = cursor.fetchone()
        return exists is not None

    def _create_database(self, cursor):
        stmt = f"""CREATE USER {self.db_user} WITH PASSWORD '{self.db_pass}';"""
        cursor.execute(stmt)
        stmt = f"""CREATE DATABASE {self.db_name} WITH OWNER {self.db_user};"""
        cursor.execute(stmt)
