# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for startup reconciliation (mocked nft)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from hop3_rootd.exec import CommandResult
from hop3_rootd.nft import rule as nft_rule, table as nft_table
from hop3_rootd.reconcile import reconcile
from hop3_rootd.state import State, StoredRule


@pytest.fixture
def patched_nft():
    with (
        patch.object(nft_rule, "find_nft_binary", return_value="/usr/sbin/nft"),
        patch.object(nft_table, "find_nft_binary", return_value="/usr/sbin/nft"),
    ):
        yield


def _ok(stdout: str = "") -> CommandResult:
    return CommandResult(argv=[], returncode=0, stdout=stdout, stderr="")


def _list_output(*entries: tuple[int, str | None]) -> str:
    """Build a fake `nft -j list table` JSON output. Entries are (handle, comment)."""
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


def _stored(rule_id: str, port: int = 80, app: str = "myapp") -> StoredRule:
    return StoredRule(
        rule_id=rule_id,
        spec={
            "port": port,
            "protocol": "tcp",
            "source": "any",
            "app_name": app,
        },
        applied_at="2026-04-24T00:00:00Z",
        status="applied",
    )


# --- All-verified case ---------------------------------------------------


def test_reconcile_all_verified(patched_nft):
    """state and kernel both have the same rules — nothing to change."""
    state = State()
    state.rules.append(_stored("r1"))
    state.rules.append(_stored("r2"))

    with patch.object(nft_rule, "exec_run") as mock_exec:
        # ensure_table (add table OK), ensure_chain (OK), list_rules
        mock_exec.side_effect = [
            _ok(),  # add table
            _ok(),  # add chain
            _ok(
                stdout=_list_output(
                    (4, "hop3:rule:r1"),
                    (7, "hop3:rule:r2"),
                )
            ),
        ]
        report = reconcile(state)

    assert report.verified == 2
    assert report.reapplied == 0
    assert report.orphans_removed == 0
    assert report.state_dropped == 0
    assert len(state.rules) == 2


# --- Re-apply missing rule -----------------------------------------------


def test_reconcile_reapplies_missing_kernel_rule(patched_nft):
    """state has r1, kernel doesn't. r1 gets re-applied."""
    state = State()
    state.rules.append(_stored("r1", port=8448, app="matrix"))

    with patch.object(nft_rule, "exec_run") as mock_exec:
        mock_exec.side_effect = [
            _ok(),  # add table
            _ok(),  # add chain
            _ok(stdout=_list_output()),  # empty kernel
            _ok(),  # nft add rule (re-apply)
        ]
        report = reconcile(state)

    assert report.verified == 0
    assert report.reapplied == 1
    assert len(state.rules) == 1


# --- Drop unparseable state rule -----------------------------------------


def test_reconcile_drops_state_with_invalid_spec(patched_nft):
    """Rule in state with malformed spec → can't be re-applied; dropped."""
    state = State()
    state.rules.append(
        StoredRule(
            rule_id="r1",
            spec={"port": 99999, "protocol": "tcp", "source": "any", "app_name": "bad"},
            applied_at="2026-04-24T00:00:00Z",
        )
    )

    with patch.object(nft_rule, "exec_run") as mock_exec:
        mock_exec.side_effect = [
            _ok(),  # add table
            _ok(),  # add chain
            _ok(stdout=_list_output()),  # empty kernel
        ]
        report = reconcile(state)

    assert report.state_dropped == 1
    assert state.rules == []


# --- Remove kernel orphan ------------------------------------------------


def test_reconcile_removes_orphan_kernel_rule(patched_nft):
    """Rule in kernel with hop3:rule comment, not in state — orphan; removed."""
    state = State()  # empty state

    with patch.object(nft_rule, "exec_run") as mock_exec:
        mock_exec.side_effect = [
            _ok(),  # add table
            _ok(),  # add chain
            _ok(stdout=_list_output((4, "hop3:rule:orphan-1"))),
            _ok(),  # delete rule
        ]
        report = reconcile(state)

    assert report.orphans_removed == 1
    assert state.rules == []


# --- Remove foreign rule (no marker) -------------------------------------


def test_reconcile_removes_foreign_rule_with_no_marker(patched_nft):
    """Rule in our table without a hop3:rule comment — foreign; removed."""
    state = State()

    with patch.object(nft_rule, "exec_run") as mock_exec:
        mock_exec.side_effect = [
            _ok(),  # add table
            _ok(),  # add chain
            _ok(stdout=_list_output((9, None))),  # foreign — no comment
            _ok(),  # delete
        ]
        report = reconcile(state)

    assert report.orphans_removed == 1


def test_reconcile_removes_foreign_rule_with_unrelated_comment(patched_nft):
    """Comment that doesn't start with hop3:rule: — foreign; removed."""
    state = State()

    with patch.object(nft_rule, "exec_run") as mock_exec:
        mock_exec.side_effect = [
            _ok(),  # add table
            _ok(),  # add chain
            _ok(stdout=_list_output((9, "operator-manual-rule"))),
            _ok(),  # delete
        ]
        report = reconcile(state)

    assert report.orphans_removed == 1


# --- Mixed scenario ------------------------------------------------------


def test_reconcile_mixed_state(patched_nft):
    """Verified + reapplied + orphan in one pass."""
    state = State()
    state.rules.extend([
        _stored("r1"),  # verified
        _stored("r2", port=80),  # missing → reapplied
    ])

    with patch.object(nft_rule, "exec_run") as mock_exec:
        mock_exec.side_effect = [
            _ok(),  # add table
            _ok(),  # add chain
            _ok(
                stdout=_list_output(
                    (4, "hop3:rule:r1"),
                    (8, "hop3:rule:orphan"),  # orphan
                )
            ),
            _ok(),  # reapply r2
            _ok(),  # delete orphan
        ]
        report = reconcile(state)

    assert report.verified == 1
    assert report.reapplied == 1
    assert report.orphans_removed == 1
    assert {r.rule_id for r in state.rules} == {"r1", "r2"}
