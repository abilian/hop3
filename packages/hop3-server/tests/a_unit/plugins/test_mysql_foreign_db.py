# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Provisioning must not adopt a populated database it did not create.

Regression: a server rebuild reclaims Hop3's own state but not MySQL's, which
is a separate service. `hop3 catalog install nextcloud` then found
`nextcloud_mysql` still holding 102 tables and an `admin` user from the app's
previous life, silently attached to it, and Nextcloud's installer failed with
"The username is already being used".

Silent adoption is the dangerous part: a brand-new app would inherit the old
one's data, including its user accounts.
"""

from __future__ import annotations

import pytest

from hop3.plugins.mysql.mysql import _refuse_foreign_database


class _Cursor:
    """Minimal cursor returning a fixed table count."""

    def __init__(self, table_count: int) -> None:
        self._table_count = table_count
        self.executed: list[tuple] = []

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.executed.append((sql, params))

    def fetchone(self) -> tuple[int]:
        return (self._table_count,)


def test_a_populated_foreign_database_is_refused() -> None:
    with pytest.raises(RuntimeError, match="102 table"):
        _refuse_foreign_database(_Cursor(102), "nextcloud_mysql", "nextcloud-mysql")


def test_the_refusal_says_how_to_proceed() -> None:
    """An operator must not have to guess; both ways out are named."""
    with pytest.raises(RuntimeError) as exc_info:
        _refuse_foreign_database(_Cursor(5), "app_mysql", "app-mysql")

    message = str(exc_info.value)
    assert "DROP DATABASE" in message
    assert "different name" in message
    assert "app_mysql" in message


def test_an_empty_leftover_is_adopted_silently() -> None:
    """
    An empty database is the common residue of a partial teardown.

    Failing on it would be noise: there is no data to inherit and nothing for an
    installer to trip over.
    """
    _refuse_foreign_database(_Cursor(0), "app_mysql", "app-mysql")  # must not raise
