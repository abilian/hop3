# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for addon env-var namespacing helpers."""

from __future__ import annotations

from dataclasses import dataclass

from hop3.deployers.addon_provisioning import (
    _effective_primary_ids,
    addon_var_prefix,
    compute_namespaced_vars,
)

DETAILS = {"DATABASE_URL": "postgresql://u:p@h:5432/d", "PGHOST": "h"}


def test_addon_var_prefix():
    assert addon_var_prefix("mydb") == "MYDB_"
    assert addon_var_prefix("my-db") == "MY_DB_"
    assert addon_var_prefix("my_db") == "MY_DB_"  # '-'/'_' alias to the same prefix


def test_namespaced_primary_is_unchanged():
    assert (
        compute_namespaced_vars(DETAILS, is_primary=True, addon_name="mydb") == DETAILS
    )


def test_namespaced_secondary_is_prefixed():
    out = compute_namespaced_vars(DETAILS, is_primary=False, addon_name="db2")
    assert out == {
        "DB2_DATABASE_URL": "postgresql://u:p@h:5432/d",
        "DB2_PGHOST": "h",
    }


# --- _effective_primary_ids ----------------------------------------------


@dataclass
class _Cred:
    id: int
    addon_type: str
    is_primary: bool = False


def test_effective_primary_uses_explicit_flag():
    creds = [_Cred(1, "postgres"), _Cred(2, "postgres", is_primary=True)]
    assert _effective_primary_ids(creds) == {2}


def test_effective_primary_falls_back_to_oldest_when_none_flagged():
    # Legacy/unflagged rows: the oldest of each type is the effective primary.
    creds = [_Cred(3, "postgres"), _Cred(1, "postgres"), _Cred(5, "redis")]
    assert _effective_primary_ids(creds) == {1, 5}


def test_effective_primary_per_type():
    creds = [
        _Cred(1, "postgres", is_primary=True),
        _Cred(2, "postgres"),
        _Cred(3, "redis", is_primary=True),
    ]
    assert _effective_primary_ids(creds) == {1, 3}
