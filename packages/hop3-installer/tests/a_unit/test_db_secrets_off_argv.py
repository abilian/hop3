# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Database passwords reach `psql` and `mysql` on stdin, never on argv.

`psql -c "ALTER USER postgres PASSWORD '...'"` and `mysql -e "CREATE USER
... IDENTIFIED BY '...'"` put the password on the command line, which any
local user reads in /proc/<pid>/cmdline while the command runs.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from hop3_installer.common import run_cmd
from hop3_installer.server_installer import mysql, postgres

PASSWORD = "hop3_" + "a" * 32


def test_run_cmd_hands_stdin_text_to_the_command():
    assert run_cmd(["cat"], stdin_text="on stdin").stdout == "on stdin"


def test_without_stdin_text_a_command_gets_eof():
    """A command that tries to prompt must fail fast, not wait on a terminal."""
    assert run_cmd(["cat"]).stdout == ""


def _recording(calls):
    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs.get("stdin_text")))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    return fake_run


def test_the_postgres_superuser_password_is_not_on_argv():
    calls: list = []
    with patch.object(postgres, "run_cmd", side_effect=_recording(calls)):
        postgres._set_postgres_password(PASSWORD)

    assert not any(PASSWORD in " ".join(cmd) for cmd, _ in calls)
    assert any(stdin and PASSWORD in stdin for _, stdin in calls)


def test_mysql_admin_statements_are_not_on_argv():
    calls: list = []
    sql = f"CREATE USER 'hop3'@'localhost' IDENTIFIED BY '{PASSWORD}';"
    with patch.object(mysql, "run_cmd", side_effect=_recording(calls)):
        mysql._run_admin_sql(["mysql", "-u", "root"], {}, sql, "create the user")

    assert calls == [(["mysql", "-u", "root"], sql)]


def test_the_hop3_mysql_user_takes_the_servers_default_plugin():
    """
    MySQL 8.4 (Ubuntu 26.04) does not load `mysql_native_password`, so a user
    created with it failed: "Plugin 'mysql_native_password' is not loaded".
    """
    calls: list = []
    with patch.object(mysql, "run_cmd", side_effect=_recording(calls)):
        mysql._create_mysql_hop3_user(["mysql"], {}, PASSWORD)

    creates = [sql for _, sql in calls if sql.startswith("CREATE USER")]
    assert creates == [
        f"CREATE USER 'hop3'@'{host}' IDENTIFIED BY '{PASSWORD}';"
        for host in ("localhost", "127.0.0.1")
    ]
