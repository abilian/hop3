# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


@dataclass(frozen=True)
class PostgresqlAddon:
    app_name: str
    settings: dict

    def create(self) -> None:
        """Create a new PostgreSQL database if it does not already exist."""

        # Create the database connection parameters
        params = {
            # 'dbname': self.db_name,  # Database name is omitted intentionally
            "user": self.settings["pg_user"],
            "password": self.settings["pg_pw"],
            "host": "localhost",
            "port": 5432,
        }

        # Establish a connection to the PostgreSQL server
        connection = psycopg2.connect(**params)
        connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

        with connection.cursor() as cursor:
            if self._check_database_exists(cursor):
                # No need to create if the database already exists
                return

            # Create the database if it does not exist
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
        """Construct the environment variables for database connection.

        Returns:
        - A dictionary with the environment variable 'DATABASE_URL' pointing to the database connection string.
        """
        return {
            "DATABASE_URL": (
                f"postgresql://{self.db_user}:{self.db_pass}@localhost/{self.db_name}"
            ),
        }

    def _check_database_exists(self, cursor) -> bool:
        """Check if the specified database exists.

        Input:
        - cursor: A database cursor object used to execute SQL queries.

        Returns:
        - bool: True if the database exists, False otherwise.
        """
        dbname = self.db_name
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
        exists = cursor.fetchone()
        return exists is not None

    def _create_database(self, cursor) -> None:
        """Create a new database and a database user with the specified
        credentials.

        Input:
        - cursor: A database cursor object that allows execution of database commands.
        """
        # SQL statement to create a new user with the specified password
        stmt = f"""CREATE USER {self.db_user} WITH PASSWORD '{self.db_pass}';"""
        cursor.execute(stmt)

        # SQL statement to create a new database with the specified owner
        stmt = f"""CREATE DATABASE {self.db_name} WITH OWNER {self.db_user};"""
        cursor.execute(stmt)
