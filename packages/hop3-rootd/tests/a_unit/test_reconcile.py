# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for startup reconciliation.

The exec seam is faked (``FakeExec``); nft never runs. Tests route the
``list`` call to a canned kernel ruleset and assert on the ReconcileReport
plus the post-reconcile state.
"""

from __future__ import annotations

import json

from hop3_rootd.reconcile import reconcile
from hop3_rootd.state import State, StoredRule

from tests.a_unit._fakes import FakeExec, ok


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


def _fake_with(*kernel_entries: tuple[int, str | None]) -> FakeExec:
    """
    A FakeExec whose ``list`` call returns the given kernel ruleset.

    All other nft invocations (add table, add chain, re-apply, delete)
    succeed with the default empty ok().
    """
    return FakeExec().on(
        lambda argv: "list" in argv, ok(stdout=_list_output(*kernel_entries))
    )


# --- All-verified case ---------------------------------------------------


def test_reconcile_all_verified():
    """state and kernel both have the same rules — nothing to change."""
    state = State()
    state.rules.append(_stored("r1"))
    state.rules.append(_stored("r2"))

    report = reconcile(state, exec=_fake_with((4, "hop3:rule:r1"), (7, "hop3:rule:r2")))

    assert report.verified == 2
    assert report.reapplied == 0
    assert report.orphans_removed == 0
    assert report.state_dropped == 0
    assert len(state.rules) == 2


# --- Re-apply missing rule -----------------------------------------------


def test_reconcile_reapplies_missing_kernel_rule():
    """state has r1, kernel doesn't. r1 gets re-applied."""
    state = State()
    state.rules.append(_stored("r1", port=8448, app="matrix"))

    report = reconcile(state, exec=_fake_with())  # empty kernel

    assert report.verified == 0
    assert report.reapplied == 1
    assert len(state.rules) == 1


# --- Drop unparseable state rule -----------------------------------------


def test_reconcile_drops_state_with_invalid_spec():
    """Rule in state with malformed spec → can't be re-applied; dropped."""
    state = State()
    state.rules.append(
        StoredRule(
            rule_id="r1",
            spec={"port": 99999, "protocol": "tcp", "source": "any", "app_name": "bad"},
            applied_at="2026-04-24T00:00:00Z",
        )
    )

    report = reconcile(state, exec=_fake_with())

    assert report.state_dropped == 1
    assert state.rules == []


# --- Remove kernel orphan ------------------------------------------------


def test_reconcile_removes_orphan_kernel_rule():
    """Rule in kernel with hop3:rule comment, not in state — orphan; removed."""
    state = State()  # empty state

    fake = _fake_with((4, "hop3:rule:orphan-1"))
    report = reconcile(state, exec=fake)

    assert report.orphans_removed == 1
    assert state.rules == []
    assert fake.calls_with("delete")  # orphan removal actually issued


# --- Remove foreign rule (no marker) -------------------------------------


def test_reconcile_removes_foreign_rule_with_no_marker():
    """Rule in our table without a hop3:rule comment — foreign; removed."""
    fake = _fake_with((9, None))  # foreign — no comment
    report = reconcile(State(), exec=fake)
    assert report.orphans_removed == 1
    assert fake.calls_with("delete")


def test_reconcile_removes_foreign_rule_with_unrelated_comment():
    """Comment that doesn't start with hop3:rule: — foreign; removed."""
    fake = _fake_with((9, "operator-manual-rule"))
    report = reconcile(State(), exec=fake)
    assert report.orphans_removed == 1


# --- Mixed scenario ------------------------------------------------------


def test_reconcile_mixed_state():
    """Verified + reapplied + orphan in one pass."""
    state = State()
    state.rules.extend([
        _stored("r1"),  # verified
        _stored("r2", port=80),  # missing → reapplied
    ])

    fake = _fake_with((4, "hop3:rule:r1"), (8, "hop3:rule:orphan"))
    report = reconcile(state, exec=fake)

    assert report.verified == 1
    assert report.reapplied == 1
    assert report.orphans_removed == 1
    assert {r.rule_id for r in state.rules} == {"r1", "r2"}
