# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Two addons never share a database or a user, and none adopts another's data.

``a-b`` and ``a_b`` both derive the database ``a_b``; MySQL cuts user names to
32 characters and PostgreSQL identifiers to 63. A second create on a shared
identifier reset the first addon's password (and, in MySQL, granted its user
the second database). A PostgreSQL database left populated by a previous app
was adopted and its owner's password reset.
"""

from __future__ import annotations

import psycopg2
import pytest

from hop3.config import HopConfig
from hop3.plugins.addons.secrets import save_addon_secrets
from hop3.plugins.mysql import mysql as my
from hop3.plugins.mysql.mysql import MySQLAddon
from hop3.plugins.postgresql import postgres as pg
from hop3.plugins.postgresql.postgres import PostgresAddon, _refuse_foreign_database


@pytest.fixture(autouse=True)
def registry(tmp_path, monkeypatch):
    """An empty addon registry; any connection to a database server fails the test."""
    monkeypatch.setattr(HopConfig, "_instance", HopConfig(hop3_root=tmp_path))

    def no_server(*args, **kwargs):
        msg = "the refusal must come before any connection"
        raise AssertionError(msg)

    monkeypatch.setattr(pg.psycopg2, "connect", no_server)
    monkeypatch.setattr(my.mysql.connector, "connect", no_server)


@pytest.mark.parametrize(
    ("existing", "new"),
    [
        ("shop-db", "shop_db"),
        # The role keeps 63 characters: x*60 + "_us" either way.
        ("x" * 60, "x" * 60 + "-us"),
    ],
)
def test_postgres_refuses_a_name_whose_identifiers_are_taken(existing, new):
    save_addon_secrets("postgres", existing, {"password": "pw"})

    with pytest.raises(ValueError, match=f"existing postgres addon '{existing}'"):
        PostgresAddon(addon_name=new).create()


@pytest.mark.parametrize(
    ("existing", "new"),
    [
        ("shop-db", "shop_db"),
        # Users keep 32 characters: "a_very_long_application_name_for".
        (
            "a-very-long-application-name-for-shop",
            "a-very-long-application-name-for-blog",
        ),
    ],
)
def test_mysql_refuses_a_name_whose_identifiers_are_taken(existing, new):
    assert MySQLAddon(addon_name=existing).db_user == MySQLAddon(addon_name=new).db_user

    save_addon_secrets("mysql", existing, {"password": "pw"})

    with pytest.raises(ValueError, match=f"existing mysql addon '{existing}'"):
        MySQLAddon(addon_name=new).create()


@pytest.mark.parametrize("addon_cls", [PostgresAddon, MySQLAddon])
def test_a_distinct_name_or_another_type_is_no_clash(addon_cls):
    save_addon_secrets("redis", "shop-db", {"password": "pw"})
    save_addon_secrets(addon_cls.name, "shop-web", {"password": "pw"})

    addon_cls(addon_name="shop_db")._refuse_identifier_clash()  # must not raise


@pytest.mark.parametrize("addon_cls", [PostgresAddon, MySQLAddon])
def test_an_existing_addon_keeps_deploying(addon_cls):
    """A pair that already shares identifiers is not locked out of redeploys."""
    save_addon_secrets(addon_cls.name, "shop-db", {"password": "pw"})
    save_addon_secrets(addon_cls.name, "shop_db", {"password": "pw"})

    addon_cls(addon_name="shop_db")._refuse_identifier_clash()  # must not raise


def test_mysql_user_name_is_unchanged_for_existing_addons():
    """A rename would leave every deployed long-named addon with no user."""
    long = MySQLAddon(addon_name="a-very-long-application-name-for-shop")
    assert long.db_user == "a_very_long_application_name_for"
    assert MySQLAddon(addon_name="shop-db").db_user == "shop_db_user"


class _Cursor:
    def __init__(self, table_count: int) -> None:
        self._table_count = table_count

    def execute(self, sql: str, params: tuple = ()) -> None:
        pass

    def fetchone(self) -> tuple[int]:
        return (self._table_count,)


def test_postgres_refuses_a_populated_foreign_database():
    with pytest.raises(RuntimeError, match="left over from a previous app"):
        _refuse_foreign_database(_Cursor(12), "shop_db", "shop-db")


def test_postgres_adopts_an_empty_leftover():
    _refuse_foreign_database(_Cursor(0), "shop_db", "shop-db")  # must not raise


def test_postgres_exists_does_not_answer_no_when_the_server_is_down(monkeypatch):
    """'Does not exist' makes `addon destroy` exit 0 and keep the database."""

    def refused(**kwargs):
        msg = "connection refused"
        raise psycopg2.OperationalError(msg)

    monkeypatch.setattr(pg.psycopg2, "connect", refused)

    with pytest.raises(psycopg2.OperationalError, match="connection refused"):
        PostgresAddon(addon_name="shop-db").exists()


class _Server:
    """A database server holding ``names`` (databases, roles, users) as state."""

    def __init__(self, *names: str, refuse: str = "") -> None:
        self.names = set(names)
        self.refuse = refuse  # a statement prefix the server rejects
        self.executed: list[str] = []
        self._found = False

    def connect(self, **kwargs):
        return self

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        pass

    def execute(self, statement, params: tuple = ()) -> None:
        statement = str(statement)  # psycopg2 statements are `sql.Composed`
        self.executed.append(statement)
        if self.refuse and statement.startswith(self.refuse):
            raise my.mysql.connector.Error(msg="denied")
        self._found = any(p in self.names for p in params)

    def fetchone(self):
        return (1,) if self._found else None

    def set_isolation_level(self, level) -> None:
        pass

    def commit(self) -> None:
        pass

    def close(self) -> None:
        pass


class _Admin:
    def get_connection_params(self, **kwargs) -> dict:
        return {}


@pytest.fixture
def no_admin_config(monkeypatch):
    monkeypatch.setattr(PostgresAddon, "_get_admin", lambda self: _Admin())
    monkeypatch.setattr(MySQLAddon, "_get_admin", lambda self: _Admin())


@pytest.mark.parametrize(
    ("addon_cls", "module"),
    [(PostgresAddon, pg.psycopg2), (MySQLAddon, my.mysql.connector)],
)
def test_a_user_left_by_a_half_failed_create_exists(
    monkeypatch, no_admin_config, addon_cls, module
):
    """`create` makes the user first: a failure after it left one destroy skipped."""
    server = _Server("shop_db_user")
    monkeypatch.setattr(module, "connect", server.connect)

    assert addon_cls(addon_name="shop-db").exists()


@pytest.mark.parametrize("addon_cls", [PostgresAddon, MySQLAddon])
def test_a_secrets_file_alone_is_an_addon(addon_cls):
    # The autouse fixture fails any connection: the file is answer enough.
    save_addon_secrets(addon_cls.name, "shop-db", {"password": "pw"})

    assert addon_cls(addon_name="shop-db").exists()


@pytest.mark.parametrize(
    ("addon_cls", "module"),
    [(PostgresAddon, pg.psycopg2), (MySQLAddon, my.mysql.connector)],
)
def test_nothing_left_is_no_addon(monkeypatch, no_admin_config, addon_cls, module):
    monkeypatch.setattr(module, "connect", _Server("other_db").connect)

    assert not addon_cls(addon_name="shop-db").exists()


@pytest.mark.parametrize(
    ("addon_cls", "module"),
    [(PostgresAddon, pg.psycopg2), (MySQLAddon, my.mysql.connector)],
)
def test_destroy_drops_a_user_without_its_database(
    monkeypatch, no_admin_config, addon_cls, module
):
    server = _Server("shop_db_user")
    monkeypatch.setattr(module, "connect", server.connect)

    addon_cls(addon_name="shop-db").destroy()

    assert any("DROP USER IF EXISTS" in s for s in server.executed)


def test_mysql_destroy_reports_a_user_it_could_not_drop(monkeypatch, no_admin_config):
    save_addon_secrets("mysql", "shop-db", {"password": "pw"})
    server = _Server(refuse="DROP USER")
    monkeypatch.setattr(my.mysql.connector, "connect", server.connect)
    addon = MySQLAddon(addon_name="shop-db")

    with pytest.raises(RuntimeError, match="can't drop the users"):
        addon.destroy()
    assert addon.exists()  # the secrets are kept, so the destroy can be retried
