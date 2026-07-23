# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Tests for the revived `addon <type> <verb>` plugin commands.

Covers both behaviour (each command dispatches to the right Addon method and
returns the right response shape) and discovery (the `cli_commands()` hook
contributes them to the RPC dispatch table).
"""

from __future__ import annotations

import base64
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

    def run_sql(self, statement: str) -> dict:
        self.calls.append(("run_sql", statement))
        # A result set with a non-string + None cell, to exercise stringifying.
        return {"columns": ["n"], "rows": [[1], [None]]}

    def run_command(self, command: str) -> str:
        self.calls.append(("run_command", command))
        return "PONG"

    def run_admin_sql(self, statement: str) -> dict:
        self.calls.append(("run_admin_sql", statement))
        return {"columns": ["c"], "rows": [["v"]]}

    def create(self) -> None:
        self.calls.append(("create",))

    def exists(self) -> bool:
        return False


class _FakeStatusAddon:
    """Addon whose run_sql() returns a status (no result set)."""

    def run_sql(self, statement: str) -> dict:
        return {"message": "OK (5 row(s) affected)"}


class _FakeExistingAddon:
    """Addon that already exists (for the clone-refuses-existing test)."""

    def exists(self) -> bool:
        return True


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


def test_sql_query_renders_table_with_stringified_cells(monkeypatch):
    fake = FakeAddon()
    monkeypatch.setattr(pg_cli, "get_addon", lambda t, n: fake)

    out = pg_cli.AddonPostgresQueryCmd().call("mydb", "--command", "SELECT n FROM t")

    assert ("run_sql", "SELECT n FROM t") in fake.calls
    tbl = next(i for i in out if i["t"] == "table")
    assert tbl["headers"] == ["n"]
    # int -> "1", None -> "" (JSON-safe over RPC)
    assert tbl["rows"] == [["1"], [""]]


def test_sql_query_renders_status_for_non_select(monkeypatch):
    monkeypatch.setattr(mysql_cli, "get_addon", lambda t, n: _FakeStatusAddon())
    out = mysql_cli.AddonMysqlQueryCmd().call("mydb", "--command", "DELETE FROM t")
    assert out[0]["t"] == "text"
    assert "row(s) affected" in out[0]["text"]


def test_redis_query_returns_text(monkeypatch):
    fake = FakeAddon()
    monkeypatch.setattr(redis_cli, "get_addon", lambda t, n: fake)

    out = redis_cli.AddonRedisQueryCmd().call("mycache", "--command", "PING")

    assert ("run_command", "PING") in fake.calls
    assert out[0]["t"] == "text"
    assert out[0]["text"] == "PONG"


def test_query_without_command_returns_usage():
    out = pg_cli.AddonPostgresQueryCmd().call("mydb")  # no --command
    assert "Usage:" in out[0]["text"]


def test_diagnostics_use_superuser_path_and_right_queries(monkeypatch):
    fake = FakeAddon()
    monkeypatch.setattr(pg_cli, "get_addon", lambda t, n: fake)

    table_ps = pg_cli.AddonPostgresPsCmd().call("mydb")
    pg_cli.AddonPostgresLocksCmd().call("mydb")
    pg_cli.AddonPostgresSettingsCmd().call("mydb")

    sqls = [stmt for (method, stmt) in fake.calls if method == "run_admin_sql"]
    assert any("pg_stat_activity" in s for s in sqls)
    assert any("pg_locks" in s for s in sqls)
    assert any("pg_settings" in s for s in sqls)
    # diagnostics render their result as a table and are read-only
    assert table_ps[0]["t"] == "table"
    assert pg_cli.AddonPostgresPsCmd.destructive is False


def test_diagnostic_missing_name_returns_usage():
    out = pg_cli.AddonPostgresPsCmd().call()
    assert "Usage:" in out[0]["text"]


def test_mysql_diagnostics_use_admin_path(monkeypatch):
    fake = FakeAddon()
    monkeypatch.setattr(mysql_cli, "get_addon", lambda t, n: fake)

    out = mysql_cli.AddonMysqlPsCmd().call("mydb")
    mysql_cli.AddonMysqlSettingsCmd().call("mydb")

    sqls = [stmt for (method, stmt) in fake.calls if method == "run_admin_sql"]
    assert any("processlist" in s.lower() for s in sqls)
    assert any("variables" in s.lower() for s in sqls)
    assert out[0]["t"] == "table"


def test_clone_creates_target_and_copies_data(monkeypatch):
    fake = FakeAddon()
    monkeypatch.setattr(pg_cli, "get_addon", lambda t, n: fake)

    out = pg_cli.AddonPostgresCloneCmd().call("prod-db", "staging-db")

    methods = [c[0] for c in fake.calls]
    assert "create" in methods  # target created
    assert "backup" in methods  # source dumped
    assert "restore" in methods  # loaded into target
    assert "summary" in _types(out)


def test_clone_refuses_existing_target(monkeypatch):
    monkeypatch.setattr(pg_cli, "get_addon", lambda t, n: _FakeExistingAddon())

    out = pg_cli.AddonPostgresCloneCmd().call("prod-db", "staging-db")

    assert out[0]["t"] == "error"
    assert "already exists" in out[0]["text"]


def test_clone_missing_args_returns_usage():
    out = pg_cli.AddonPostgresCloneCmd().call("only-source")
    assert "Usage:" in out[0]["text"]


def test_export_streams_dump_as_blob(monkeypatch, tmp_path):
    dump = tmp_path / "d.sql"
    dump.write_bytes(b"SELECT 1;\n")

    class _Exporter:
        def backup(self):
            return dump

    monkeypatch.setattr(pg_cli, "get_addon", lambda t, n: _Exporter())

    out = pg_cli.AddonPostgresExportCmd().call("mydb")

    blob = next(i for i in out if i["t"] == "blob")
    assert base64.b64decode(blob["data"]) == b"SELECT 1;\n"


def test_import_restores_decoded_dump_and_is_destructive(monkeypatch):
    seen = {}

    class _Importer:
        def restore(self, path):
            seen["content"] = Path(path).read_bytes()

    monkeypatch.setattr(pg_cli, "get_addon", lambda t, n: _Importer())

    assert pg_cli.AddonPostgresImportCmd.destructive is True
    payload = base64.b64encode(b"CREATE TABLE t();").decode()
    pg_cli.AddonPostgresImportCmd().call("mydb", import_data=payload)

    assert seen["content"] == b"CREATE TABLE t();"


def test_import_without_data_returns_error():
    out = pg_cli.AddonPostgresImportCmd().call("mydb")  # no import_data
    assert out[0]["t"] == "error"
    assert "Pipe one on stdin" in out[0]["text"]


def test_redis_info_uses_run_command(monkeypatch):
    fake = FakeAddon()
    monkeypatch.setattr(redis_cli, "get_addon", lambda t, n: fake)

    out = redis_cli.AddonRedisInfoCmd().call("mycache")

    assert ("run_command", "INFO") in fake.calls
    assert out[0]["t"] == "text"


# --- redis / s3 now have a restore path (reviewer P1) ------------------------


def test_redis_restore_calls_restore_and_is_destructive(monkeypatch):
    fake = FakeAddon()
    monkeypatch.setattr(redis_cli, "get_addon", lambda t, n: fake)

    assert redis_cli.AddonRedisRestoreCmd.destructive is True
    redis_cli.AddonRedisRestoreCmd().call("mycache", "/tmp/dump.rdb")

    assert ("restore", Path("/tmp/dump.rdb")) in fake.calls


def test_redis_clone_creates_target_and_copies_data(monkeypatch):
    fake = FakeAddon()
    monkeypatch.setattr(redis_cli, "get_addon", lambda t, n: fake)

    out = redis_cli.AddonRedisCloneCmd().call("prod-cache", "staging-cache")

    methods = [c[0] for c in fake.calls]
    assert {"create", "backup", "restore"} <= set(methods)
    assert "summary" in _types(out)


def test_redis_import_restores_decoded_dump_and_is_destructive(monkeypatch):
    seen = {}

    class _Importer:
        def restore(self, path):
            seen["content"] = Path(path).read_bytes()

    monkeypatch.setattr(redis_cli, "get_addon", lambda t, n: _Importer())

    assert redis_cli.AddonRedisImportCmd.destructive is True
    payload = base64.b64encode(b"REDISDUMP").decode()
    redis_cli.AddonRedisImportCmd().call("mycache", import_data=payload)

    assert seen["content"] == b"REDISDUMP"


def test_redis_export_streams_dump_as_blob(monkeypatch, tmp_path):
    dump = tmp_path / "d.rdb"
    dump.write_bytes(b"\x00rdb\x00")

    class _Exporter:
        def backup(self):
            return dump

    monkeypatch.setattr(redis_cli, "get_addon", lambda t, n: _Exporter())

    out = redis_cli.AddonRedisExportCmd().call("mycache")
    blob = next(i for i in out if i["t"] == "blob")
    assert base64.b64decode(blob["data"]) == b"\x00rdb\x00"


def test_s3_restore_calls_restore_and_is_destructive(monkeypatch):
    fake = FakeAddon()
    monkeypatch.setattr(s3_cli, "get_addon", lambda t, n: fake)

    assert s3_cli.AddonS3RestoreCmd.destructive is True
    s3_cli.AddonS3RestoreCmd().call("mybucket", "/tmp/bucket.dump")

    assert ("restore", Path("/tmp/bucket.dump")) in fake.calls


def test_s3_import_restores_decoded_dump(monkeypatch):
    seen = {}

    class _Importer:
        def restore(self, path):
            seen["content"] = Path(path).read_bytes()

    monkeypatch.setattr(s3_cli, "get_addon", lambda t, n: _Importer())

    assert s3_cli.AddonS3ImportCmd.destructive is True
    s3_cli.AddonS3ImportCmd().call(
        "mybucket", import_data=base64.b64encode(b"S3DUMP").decode()
    )
    assert seen["content"] == b"S3DUMP"


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
        ("addon", "redis", "query"),
        ("addon", "postgres", "query"),
        ("addon", "postgres", "ps"),
        ("addon", "postgres", "locks"),
        ("addon", "postgres", "settings"),
        ("addon", "postgres", "clone"),
        ("addon", "postgres", "export"),
        ("addon", "postgres", "import"),
        ("addon", "mysql", "query"),
        ("addon", "mysql", "ps"),
        ("addon", "mysql", "settings"),
        ("addon", "mysql", "clone"),
        ("addon", "mysql", "export"),
        ("addon", "mysql", "import"),
        ("addon", "postgres", "activity"),
        ("addon", "mysql", "activity"),
        ("addon", "redis", "info"),
        ("addon", "redis", "restore"),
        ("addon", "redis", "clone"),
        ("addon", "redis", "export"),
        ("addon", "redis", "import"),
        ("addon", "s3", "credentials"),
        ("addon", "s3", "dump"),
        ("addon", "s3", "restore"),
        ("addon", "s3", "clone"),
        ("addon", "s3", "export"),
        ("addon", "s3", "import"),
    }
    assert expected <= set(rpc.commands)


def test_find_command_resolves_three_token_path():
    cmd, n = rpc.find_command(["addon", "postgres", "credentials", "mydb"])
    assert cmd is rpc.commands["addon", "postgres", "credentials"]
    assert n == 3  # the trailing 'mydb' is left as the argument
