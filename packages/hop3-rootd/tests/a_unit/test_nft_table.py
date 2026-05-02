# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for nft table management."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from hop3_rootd.exec import CommandResult
from hop3_rootd.nft import rule as nft_rule, table as nft_table
from hop3_rootd.nft.rule import (
    NftCommandError,
    NftError,
)


@pytest.fixture
def patched_nft():
    """Patch find_nft_binary in BOTH namespaces — nft_table has its own
    bound reference (via `from .rule import find_nft_binary`), so patches
    in nft_rule don't propagate into nft_table's call sites.
    """
    with (
        patch.object(nft_rule, "find_nft_binary", return_value="/usr/sbin/nft"),
        patch.object(nft_table, "find_nft_binary", return_value="/usr/sbin/nft"),
    ):
        yield "/usr/sbin/nft"


# --- ensure_table_exists --------------------------------------------------


def _ok(stdout: str = "") -> CommandResult:
    return CommandResult(argv=[], returncode=0, stdout=stdout, stderr="")


def _fail(stderr: str, returncode: int = 1) -> CommandResult:
    return CommandResult(argv=[], returncode=returncode, stdout="", stderr=stderr)


def test_ensure_table_creates_when_absent(patched_nft):
    """Both add table and add chain succeed cleanly."""
    with patch.object(nft_rule, "exec_run") as mock_run:
        mock_run.side_effect = [_ok(), _ok()]
        nft_table.ensure_table_exists()
    assert mock_run.call_count == 2
    # First call: nft add table inet hop3
    args, _ = mock_run.call_args_list[0]
    assert args[0] == ["/usr/sbin/nft", "add", "table", "inet", "hop3"]
    # Second call: nft add chain inet hop3 input { ... }
    args, _ = mock_run.call_args_list[1]
    assert args[0][:6] == ["/usr/sbin/nft", "add", "chain", "inet", "hop3", "input"]


def test_ensure_table_tolerates_already_exists(patched_nft):
    """nft 'File exists' on add table → fine, idempotent."""
    with patch.object(nft_rule, "exec_run") as mock_run:
        mock_run.side_effect = [
            _fail("Error: Could not add table: File exists"),  # table already there
            _ok(),  # chain creation succeeds
        ]
        nft_table.ensure_table_exists()  # no exception


def test_ensure_table_raises_on_genuine_failure(patched_nft):
    """Non-idempotent failure (e.g. permission denied) propagates."""
    with patch.object(nft_rule, "exec_run") as mock_run:
        mock_run.return_value = _fail("Error: Operation not permitted")
        with pytest.raises(NftCommandError):
            nft_table.ensure_table_exists()


def test_ensure_table_chain_idempotent(patched_nft):
    """Chain creation also tolerates 'File exists'."""
    with patch.object(nft_rule, "exec_run") as mock_run:
        mock_run.side_effect = [
            _ok(),  # table created
            _fail("Error: Could not add chain: File exists"),  # chain already there
        ]
        nft_table.ensure_table_exists()  # no exception


# --- list_rules -----------------------------------------------------------


def test_list_rules_empty_table(patched_nft):
    output = json.dumps({
        "nftables": [
            {"table": {"family": "inet", "name": "hop3"}},
            {"chain": {"family": "inet", "name": "input"}},
        ]
    })
    with patch.object(nft_rule, "exec_run") as mock_run:
        mock_run.return_value = _ok(stdout=output)
        rules = nft_table.list_rules()
    assert rules == []


def test_list_rules_with_two_rules(patched_nft):
    output = json.dumps({
        "nftables": [
            {"table": {"family": "inet", "name": "hop3"}},
            {"chain": {"family": "inet", "name": "input"}},
            {"rule": {"handle": 4, "comment": "hop3:rule:r1", "expr": []}},
            {"rule": {"handle": 7, "comment": "hop3:rule:r2", "expr": []}},
        ]
    })
    with patch.object(nft_rule, "exec_run") as mock_run:
        mock_run.return_value = _ok(stdout=output)
        rules = nft_table.list_rules()
    assert len(rules) == 2
    assert {r.handle for r in rules} == {4, 7}


def test_list_rules_invokes_nft_with_j_flag(patched_nft):
    """We rely on -j JSON output."""
    with patch.object(nft_rule, "exec_run") as mock_run:
        mock_run.return_value = _ok(stdout='{"nftables": []}')
        nft_table.list_rules()
    args, _ = mock_run.call_args
    assert "-j" in args[0]


def test_list_rules_raises_on_invalid_json(patched_nft):
    with patch.object(nft_rule, "exec_run") as mock_run:
        mock_run.return_value = _ok(stdout="not json")
        with pytest.raises(NftError, match="not valid JSON"):
            nft_table.list_rules()


def test_list_rules_raises_on_non_dict_top_level(patched_nft):
    with patch.object(nft_rule, "exec_run") as mock_run:
        mock_run.return_value = _ok(stdout="[]")
        with pytest.raises(NftError, match="should be object"):
            nft_table.list_rules()


def test_list_rules_propagates_nft_failure(patched_nft):
    with patch.object(nft_rule, "exec_run") as mock_run:
        mock_run.return_value = _fail("table not found", returncode=1)
        with pytest.raises(NftCommandError):
            nft_table.list_rules()


# --- delete_table ---------------------------------------------------------


def test_delete_table_invokes_nft(patched_nft):
    with patch.object(nft_rule, "exec_run") as mock_run:
        mock_run.return_value = _ok()
        nft_table.delete_table()
    args, _ = mock_run.call_args
    assert args[0] == ["/usr/sbin/nft", "delete", "table", "inet", "hop3"]


def test_delete_table_idempotent_on_missing(patched_nft):
    """Deleting a missing table is a no-op success."""
    with patch.object(nft_rule, "exec_run") as mock_run:
        mock_run.return_value = _fail("Error: No such file or directory")
        nft_table.delete_table()  # no exception


def test_delete_table_raises_on_other_failure(patched_nft):
    with patch.object(nft_rule, "exec_run") as mock_run:
        mock_run.return_value = _fail("Error: Operation not permitted")
        with pytest.raises(NftCommandError):
            nft_table.delete_table()
