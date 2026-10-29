# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
A missing database driver is never reported as a passing health check.

The PostgreSQL and MySQL checks answered "driver not installed (skipped)" with
``passed=True``. The drivers are runtime dependencies of hop3-server, and the
addon modules import them unconditionally, so a missing driver fails the
plugin's import, at server start, instead of hiding behind a green check.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from hop3.plugins.mysql.plugin import MySQLHealthCheck
from hop3.plugins.postgresql.plugin import PostgresHealthCheck


@pytest.mark.parametrize(
    ("driver", "plugin_module"),
    [
        ("psycopg2", "hop3.plugins.postgresql.plugin"),
        ("mysql", "hop3.plugins.mysql.plugin"),
        ("redis", "hop3.plugins.redis.plugin"),
    ],
)
def test_a_missing_driver_fails_the_plugin_import(driver, plugin_module):
    code = (
        f"import sys; sys.modules[{driver!r}] = None\n"
        f"import importlib; importlib.import_module({plugin_module!r})"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )

    assert result.returncode != 0
    assert "ImportError" in result.stderr or "ModuleNotFoundError" in result.stderr


@pytest.mark.parametrize("check_cls", [PostgresHealthCheck, MySQLHealthCheck])
def test_is_configured_does_not_swallow_a_broken_config(check_cls, monkeypatch):
    def broken() -> None:
        msg = "POSTGRES_PORT is not a number"
        raise ValueError(msg)

    admin_cls = (
        "hop3.plugins.postgresql.plugin.PostgresAdmin"
        if check_cls is PostgresHealthCheck
        else "hop3.plugins.mysql.plugin.MySQLAdmin"
    )
    monkeypatch.setattr(f"{admin_cls}.from_config", broken)

    with pytest.raises(ValueError, match="not a number"):
        check_cls().is_configured()
