# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for firewall ops (mocked nft)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from hop3_rootd import PROTOCOL_VERSION
from hop3_rootd.exec import CommandResult
from hop3_rootd.nft import rule as nft_rule, table as nft_table
from hop3_rootd.nft.rule import NftCommandError
from hop3_rootd.ops import StateConflictError, get_handler
from hop3_rootd.ops._base import OpContext
from hop3_rootd.protocol import Request
from hop3_rootd.state import State, StoredRule
from hop3_rootd.validation import ValidationError

# --- Fixtures -------------------------------------------------------------


def _ok(stdout: str = "") -> CommandResult:
    return CommandResult(argv=[], returncode=0, stdout=stdout, stderr="")


def _fail(stderr: str, returncode: int = 1) -> CommandResult:
    return CommandResult(argv=[], returncode=returncode, stdout="", stderr=stderr)


@pytest.fixture
def patched_nft():
    """Patch find_nft_binary in BOTH namespaces."""
    with (
        patch.object(nft_rule, "find_nft_binary", return_value="/usr/sbin/nft"),
        patch.object(nft_table, "find_nft_binary", return_value="/usr/sbin/nft"),
    ):
        yield "/usr/sbin/nft"


@pytest.fixture
def ctx():
    state = State()
    saved: dict[str, int] = {"count": 0}

    def save_state():
        saved["count"] += 1

    return OpContext(
        state=state,
        state_path=None,
        save_state=save_state,
        now_iso=lambda: "2026-04-24T15:30:00+00:00",
        new_rule_id=lambda: "rule-test-1",
    )


def _add_rule_request(**args) -> Request:
    return Request(v=PROTOCOL_VERSION, id="req-1", op="firewall.add_rule", args=args)


# --- firewall.add_rule ---------------------------------------------------


def test_add_rule_happy_path(patched_nft, ctx):
    handler = get_handler("firewall.add_rule")
    assert handler is not None
    nft_list_output = (
        '{"nftables":[{"rule":{"handle":47,"comment":"hop3:rule:rule-test-1"}}]}'
    )

    with patch.object(nft_rule, "exec_run") as mock_exec:
        # Sequence of nft calls: add_rule (1), then list_rules for handle resolution (2)
        mock_exec.side_effect = [_ok(), _ok(stdout=nft_list_output)]
        result = handler(
            _add_rule_request(
                port=8448,
                protocol="tcp",
                source="any",
                app_name="matrix",
                description="federation",
            ),
            ctx,
        )

    assert result["rule_id"] == "rule-test-1"
    assert result["spec"]["port"] == 8448
    assert result["spec"]["protocol"] == "tcp"
    assert result["spec"]["app_name"] == "matrix"
    assert result["spec"]["description"] == "federation"
    assert result["nft_handle"] == 47
    assert result["table"] == "inet hop3"
    # State has the rule, status applied.
    assert len(ctx.state.rules) == 1
    assert ctx.state.rules[0].rule_id == "rule-test-1"
    assert ctx.state.rules[0].status == "applied"


def test_add_rule_validation_failure(patched_nft, ctx):
    """Bad spec → ValidationError raised, no nft call, no state change."""
    handler = get_handler("firewall.add_rule")
    assert handler is not None
    with (
        patch.object(nft_rule, "exec_run") as mock_exec,
        pytest.raises(ValidationError),
    ):
        handler(
            _add_rule_request(
                port=99999,  # out of range
                protocol="tcp",
                source="any",
                app_name="matrix",
            ),
            ctx,
        )
    mock_exec.assert_not_called()
    assert ctx.state.rules == []


def test_add_rule_rolls_back_on_nft_failure(patched_nft, ctx):
    """nft fails → pending state is rolled back, no rule remains."""
    handler = get_handler("firewall.add_rule")
    assert handler is not None
    with patch.object(nft_rule, "exec_run") as mock_exec:
        mock_exec.return_value = _fail("Error: invalid rule")
        with pytest.raises(NftCommandError):
            handler(
                _add_rule_request(
                    port=8448,
                    protocol="tcp",
                    source="any",
                    app_name="matrix",
                ),
                ctx,
            )
    assert ctx.state.rules == []  # rolled back


def test_add_rule_with_port_range(patched_nft, ctx):
    handler = get_handler("firewall.add_rule")
    assert handler is not None
    nft_list_output = (
        '{"nftables":[{"rule":{"handle":47,"comment":"hop3:rule:rule-test-1"}}]}'
    )

    with patch.object(nft_rule, "exec_run") as mock_exec:
        mock_exec.side_effect = [_ok(), _ok(stdout=nft_list_output)]
        result = handler(
            _add_rule_request(
                port_range=[49152, 65535],
                protocol="udp",
                source="any",
                app_name="matrix-turn",
            ),
            ctx,
        )
    assert result["spec"]["port_range"] == [49152, 65535]


def test_add_rule_with_cidr_source(patched_nft, ctx):
    handler = get_handler("firewall.add_rule")
    assert handler is not None
    nft_list_output = (
        '{"nftables":[{"rule":{"handle":47,"comment":"hop3:rule:rule-test-1"}}]}'
    )

    with patch.object(nft_rule, "exec_run") as mock_exec:
        mock_exec.side_effect = [_ok(), _ok(stdout=nft_list_output)]
        result = handler(
            _add_rule_request(
                port=5432,
                protocol="tcp",
                source="10.0.0.0/8",
                app_name="pgdb",
            ),
            ctx,
        )
    assert result["spec"]["source"] == "10.0.0.0/8"


# --- firewall.remove_rule ------------------------------------------------


def test_remove_rule_happy_path(patched_nft, ctx):
    """Pre-seed state with one rule, then remove it."""
    ctx.state.rules.append(
        StoredRule(
            rule_id="rule-1",
            spec={
                "port": 8448,
                "protocol": "tcp",
                "source": "any",
                "app_name": "matrix",
            },
            applied_at="2026-04-24T15:30:00+00:00",
            status="applied",
        )
    )

    handler = get_handler("firewall.remove_rule")
    assert handler is not None
    nft_list_output = (
        '{"nftables":[{"rule":{"handle":47,"comment":"hop3:rule:rule-1"}}]}'
    )

    with patch.object(nft_rule, "exec_run") as mock_exec:
        # 1: nft list (handle resolution); 2: nft delete
        mock_exec.side_effect = [_ok(stdout=nft_list_output), _ok()]
        req = Request(
            v=PROTOCOL_VERSION,
            id="r1",
            op="firewall.remove_rule",
            args={"rule_id": "rule-1"},
        )
        result = handler(req, ctx)

    assert result["removed"] is True
    assert result["rule_id"] == "rule-1"
    assert ctx.state.rules == []


def test_remove_rule_unknown_id_raises_state_conflict(patched_nft, ctx):
    handler = get_handler("firewall.remove_rule")
    assert handler is not None
    req = Request(
        v=PROTOCOL_VERSION,
        id="r1",
        op="firewall.remove_rule",
        args={"rule_id": "no-such-rule"},
    )
    with pytest.raises(StateConflictError, match="not found in state"):
        handler(req, ctx)


def test_remove_rule_kernel_already_absent(patched_nft, ctx):
    """State has the rule but kernel doesn't — clean up state and report."""
    ctx.state.rules.append(
        StoredRule(
            rule_id="rule-1",
            spec={"port": 80, "protocol": "tcp", "source": "any", "app_name": "web"},
            applied_at="2026-04-24T15:30:00+00:00",
            status="applied",
        )
    )
    # Mock list_rules to return empty.
    handler = get_handler("firewall.remove_rule")
    assert handler is not None
    with patch.object(nft_rule, "exec_run") as mock_exec:
        mock_exec.return_value = _ok(stdout='{"nftables":[]}')
        req = Request(
            v=PROTOCOL_VERSION,
            id="r1",
            op="firewall.remove_rule",
            args={"rule_id": "rule-1"},
        )
        result = handler(req, ctx)
    assert result["removed"] is True
    assert result["kernel_state"] == "absent"
    assert ctx.state.rules == []  # also cleaned from state


def test_remove_rule_invalid_id_type_raises_validation(patched_nft, ctx):
    handler = get_handler("firewall.remove_rule")
    assert handler is not None
    req = Request(
        v=PROTOCOL_VERSION,
        id="r1",
        op="firewall.remove_rule",
        args={"rule_id": 12345},  # not a string
    )
    with pytest.raises(ValidationError):
        handler(req, ctx)


# --- firewall.list_rules -------------------------------------------------


def test_list_rules_empty(ctx):
    handler = get_handler("firewall.list_rules")
    assert handler is not None
    req = Request(v=PROTOCOL_VERSION, id="r1", op="firewall.list_rules", args={})
    result = handler(req, ctx)
    assert result == {"rules": []}


def test_list_rules_returns_all(ctx):
    ctx.state.rules.extend([
        StoredRule("r1", {"app_name": "matrix", "port": 8448}, "2026-04-24T00:00:00Z"),
        StoredRule("r2", {"app_name": "other", "port": 80}, "2026-04-24T00:00:00Z"),
    ])
    handler = get_handler("firewall.list_rules")
    assert handler is not None
    req = Request(v=PROTOCOL_VERSION, id="r1", op="firewall.list_rules", args={})
    result = handler(req, ctx)
    assert len(result["rules"]) == 2


def test_list_rules_filters_by_app_name(ctx):
    ctx.state.rules.extend([
        StoredRule("r1", {"app_name": "matrix", "port": 8448}, "2026-04-24T00:00:00Z"),
        StoredRule("r2", {"app_name": "other", "port": 80}, "2026-04-24T00:00:00Z"),
        StoredRule("r3", {"app_name": "matrix", "port": 3478}, "2026-04-24T00:00:00Z"),
    ])
    handler = get_handler("firewall.list_rules")
    assert handler is not None
    req = Request(
        v=PROTOCOL_VERSION,
        id="r1",
        op="firewall.list_rules",
        args={"app_name": "matrix"},
    )
    result = handler(req, ctx)
    assert len(result["rules"]) == 2
    assert {r["rule_id"] for r in result["rules"]} == {"r1", "r3"}


def test_list_rules_validates_app_name_filter(ctx):
    handler = get_handler("firewall.list_rules")
    assert handler is not None
    req = Request(
        v=PROTOCOL_VERSION,
        id="r1",
        op="firewall.list_rules",
        args={"app_name": "INVALID NAME"},
    )
    with pytest.raises(ValidationError):
        handler(req, ctx)
