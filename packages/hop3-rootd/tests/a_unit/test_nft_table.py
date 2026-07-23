# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for nft table management.

The exec seam is faked (``FakeExec``); these tests never invoke nft. They
assert on the recorded argv set and the parsed result, not on a fragile
mock call order.
"""

from __future__ import annotations

import json

import pytest
from hop3_rootd.nft.rule import NftCommandError, NftError
from hop3_rootd.nft.table import (
    delete_table,
    ensure_table_exists,
    list_rules,
)

from tests.a_unit._fakes import FakeExec, fail, ok

_NFT = "/usr/sbin/nft"


def _list_output(*entries: tuple[int, str | None]) -> str:
    """Build fake `nft -j list table` JSON. Entries are (handle, comment)."""
    rules = []
    for handle, comment in entries:
        rule: dict = {"handle": handle, "expr": []}
        if comment is not None:
            rule["comment"] = comment
        rules.append({"rule": rule})
    return json.dumps({
        "nftables": [
            {"table": {"family": "inet", "name": "hop3"}},
            {"chain": {"family": "inet", "name": "input"}},
            *rules,
        ]
    })


# --- ensure_table_exists --------------------------------------------------


def test_ensure_table_creates_when_absent():
    """Both add table and add chain are issued; both succeed."""
    fake = FakeExec()
    ensure_table_exists(exec=fake)
    # Table then chain — assert both commands ran (membership, not order).
    assert [_NFT, "add", "table", "inet", "hop3"] in fake.calls
    chain_calls = [
        c
        for c in fake.calls
        if c[:6] == [_NFT, "add", "chain", "inet", "hop3", "input"]
    ]
    assert len(chain_calls) == 1


def test_ensure_table_tolerates_already_exists():
    """nft 'File exists' on add table → fine, idempotent; chain still runs."""
    fake = FakeExec().on(
        lambda argv: "add" in argv and "table" in argv,
        fail("Error: Could not add table: File exists"),
    )
    ensure_table_exists(exec=fake)  # no exception
    # Chain command still issued and succeeded (default ok()).
    assert any("chain" in c for c in fake.calls)


def test_ensure_table_raises_on_genuine_failure():
    """Non-idempotent failure (e.g. permission denied) propagates."""
    fake = FakeExec().on(lambda argv: True, fail("Error: Operation not permitted"))
    with pytest.raises(NftCommandError):
        ensure_table_exists(exec=fake)


def test_ensure_table_chain_idempotent():
    """Chain creation also tolerates 'File exists'."""
    fake = FakeExec().on(
        lambda argv: "chain" in argv,
        fail("Error: Could not add chain: File exists"),
    )
    ensure_table_exists(exec=fake)  # table ok, chain tolerated → no exception


# --- list_rules -----------------------------------------------------------


def test_list_rules_empty_table():
    fake = FakeExec().on(lambda argv: "list" in argv, ok(stdout=_list_output()))
    assert list_rules(exec=fake) == []


def test_list_rules_with_two_rules():
    fake = FakeExec().on(
        lambda argv: "list" in argv,
        ok(stdout=_list_output((4, "hop3:rule:r1"), (7, "hop3:rule:r2"))),
    )
    rules = list_rules(exec=fake)
    assert {r.handle for r in rules} == {4, 7}


def test_list_rules_invokes_nft_with_j_flag():
    """We rely on -j JSON output."""
    fake = FakeExec().on(lambda argv: "list" in argv, ok(stdout='{"nftables": []}'))
    list_rules(exec=fake)
    assert "-j" in fake.calls_with("list")[0]


def test_list_rules_raises_on_invalid_json():
    fake = FakeExec().on(lambda argv: "list" in argv, ok(stdout="not json"))
    with pytest.raises(NftError, match="not valid JSON"):
        list_rules(exec=fake)


def test_list_rules_raises_on_non_dict_top_level():
    fake = FakeExec().on(lambda argv: "list" in argv, ok(stdout="[]"))
    with pytest.raises(NftError, match="should be object"):
        list_rules(exec=fake)


def test_list_rules_propagates_nft_failure():
    fake = FakeExec().on(lambda argv: "list" in argv, fail("table not found"))
    with pytest.raises(NftCommandError):
        list_rules(exec=fake)


# --- delete_table ---------------------------------------------------------


def test_delete_table_invokes_nft():
    fake = FakeExec()
    delete_table(exec=fake)
    assert [_NFT, "delete", "table", "inet", "hop3"] in fake.calls


def test_delete_table_idempotent_on_missing():
    """Deleting a missing table is a no-op success."""
    fake = FakeExec().on(lambda argv: True, fail("Error: No such file or directory"))
    delete_table(exec=fake)  # no exception


def test_delete_table_raises_on_other_failure():
    fake = FakeExec().on(lambda argv: True, fail("Error: Operation not permitted"))
    with pytest.raises(NftCommandError):
        delete_table(exec=fake)
