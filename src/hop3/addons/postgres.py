# Copyright (c) 2023-2024, Abilian SAS

from dataclasses import dataclass

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from hop3.addons.base import Addon


@dataclass(frozen=True)
class PostgresqlAddon(Addon):
    app_name: str
    settings: dict

    def create(self):
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
            if _check_database_exists(cursor, self.db_name):
                return
            stmt = f"""CREATE USER {self.db_user} WITH PASSWORD '{self.db_pass}';"""
            cursor.execute(stmt)
            stmt = f"""CREATE DATABASE {self.db_name} WITH OWNER {self.db_user};"""
            cursor.execute(stmt)
        connection.close()

    @property
    def db_name(self):
        return self.app_name + "_db"

    @property
    def db_user(self):
        return self.app_name + "_user"

    @property
    def db_pass(self):
        return self.app_name + "_pw"

    def get_env(self):
        return {
            "DATABASE_URL": f"postgresql://{self.db_user}:{self.db_pass}@localhost/{self.db_name}"
        }


def _check_database_exists(cursor, dbname):
    cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
    exists = cursor.fetchone()
    return exists is not None
