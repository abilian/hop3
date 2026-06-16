# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the revived `addon <type> <verb>` plugin commands.

Covers both behaviour (each command dispatches to the right Addon method and
returns the right response shape) and discovery (the `cli_commands()` hook
contributes them to the RPC dispatch table).
"""

from __future__ import annotations

from pathlib import Path

from hop3.plugins.mysql import cli as mysql_cli
from hop3.plugins.postgresql import cli as pg_cli
from hop3.plugins.redis import cli as redis_cli
from hop3.plugins.s3 import cli as s3_cli
from hop3.server.controllers import rpc


class FakeAddon:
    """Records calls and returns canned values for the Addon protocol."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def get_connection_details(self) -> dict[str, str]:
        return {"DATABASE_URL": "proto://user:pw@host/db", "HOST": "127.0.0.1"}

    def backup(self) -> Path:
        self.calls.append(("backup",))
        return Path("/home/hop3/backups/x.dump")

    def restore(self, path: Path) -> None:
        self.calls.append(("restore", path))

    def install_extensions(self, extensions: list[str]) -> None:
        self.calls.append(("install_extensions", extensions))

    def flush(self) -> None:
        self.calls.append(("flush",))


def _types(items: list[dict]) -> list[str]:
    return [item.get("t") for item in items]


# --- behaviour ---------------------------------------------------------------


def test_credentials_returns_table(monkeypatch):
    fake = FakeAddon()
    monkeypatch.setattr(pg_cli, "get_addon", lambda t, n: fake)

    out = pg_cli.AddonPostgresCredentialsCmd().call("mydb")

    assert "table" in _types(out)
    tbl = next(i for i in out if i["t"] == "table")
    assert tbl["headers"] == ["Variable", "Value"]
    assert ["DATABASE_URL", "proto://user:pw@host/db"] in tbl["rows"]


def test_dump_calls_backup_and_reports_path(monkeypatch):
    fake = FakeAddon()
    monkeypatch.setattr(mysql_cli, "get_addon", lambda t, n: fake)

    out = mysql_cli.AddonMysqlDumpCmd().call("mydb")

    assert ("backup",) in fake.calls
    assert "summary" in _types(out)
    assert any("/home/hop3/backups/x.dump" in i.get("text", "") for i in out)


def test_restore_calls_restore_with_path_and_is_destructive(monkeypatch):
    fake = FakeAddon()
    monkeypatch.setattr(pg_cli, "get_addon", lambda t, n: fake)

    assert pg_cli.AddonPostgresRestoreCmd.destructive is True
    pg_cli.AddonPostgresRestoreCmd().call("mydb", "/tmp/backup.sql")

    assert ("restore", Path("/tmp/backup.sql")) in fake.calls


def test_extensions_installs_listed_extensions(monkeypatch):
    fake = FakeAddon()
    monkeypatch.setattr(pg_cli, "get_addon", lambda t, n: fake)

    pg_cli.AddonPostgresExtensionsCmd().call("mydb", "postgis", "pgvector")

    assert ("install_extensions", ["postgis", "pgvector"]) in fake.calls


def test_redis_flush_calls_flush_and_is_destructive(monkeypatch):
    fake = FakeAddon()
    monkeypatch.setattr(redis_cli, "get_addon", lambda t, n: fake)

    assert redis_cli.AddonRedisFlushCmd.destructive is True
    redis_cli.AddonRedisFlushCmd().call("mycache")

    assert ("flush",) in fake.calls


def test_missing_args_returns_usage_not_crash():
    # No monkeypatch: must short-circuit on the arg guard before get_addon.
    out = s3_cli.AddonS3CredentialsCmd().call()
    assert out[0]["t"] == "text"
    assert "Usage:" in out[0]["text"]

    out = pg_cli.AddonPostgresRestoreCmd().call("only-name")  # needs 2 args
    assert "Usage:" in out[0]["text"]


# --- discovery (cli_commands hook -> RPC dispatch table) ---------------------


def test_hook_contributes_all_commands_to_rpc_table():
    expected = {
        ("addon", "postgres", "credentials"),
        ("addon", "postgres", "dump"),
        ("addon", "postgres", "restore"),
        ("addon", "postgres", "extensions"),
        ("addon", "mysql", "credentials"),
        ("addon", "mysql", "dump"),
        ("addon", "mysql", "restore"),
        ("addon", "redis", "credentials"),
        ("addon", "redis", "dump"),
        ("addon", "redis", "flush"),
        ("addon", "s3", "credentials"),
        ("addon", "s3", "dump"),
    }
    assert expected <= set(rpc.commands)


def test_find_command_resolves_three_token_path():
    cmd, n = rpc.find_command(["addon", "postgres", "credentials", "mydb"])
    assert cmd is rpc.commands["addon", "postgres", "credentials"]
    assert n == 3  # the trailing 'mydb' is left as the argument
