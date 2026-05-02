# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for nft rule construction and output parsing.

The exec wrapper is mocked here — these tests don't actually invoke nft.
Real-binary tests live in tests/b_integration/.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from hop3_rootd.nft import rule as nft_rule
from hop3_rootd.nft.rule import (
    CHAIN_NAME,
    COMMENT_PREFIX,
    TABLE_FAMILY,
    TABLE_NAME,
    KernelRule,
    NftBinaryNotFoundError,
    NftCommandError,
    build_add_argv,
    build_delete_argv,
    make_comment,
    parse_comment,
    parse_list_output,
    run_nft,
)
from hop3_rootd.validation import PortSpec

# --- Comment helpers ------------------------------------------------------


def test_make_comment_uses_prefix():
    assert make_comment("abc-123") == f"{COMMENT_PREFIX}abc-123"


def test_parse_comment_extracts_id():
    comment = make_comment("xyz-789")
    assert parse_comment(comment) == "xyz-789"


def test_parse_comment_returns_none_for_foreign():
    assert parse_comment("operator's manual rule") is None
    assert parse_comment("") is None
    assert parse_comment(None) is None


# --- find_nft_binary ------------------------------------------------------


def test_find_nft_binary_raises_when_not_on_path():
    with patch("hop3_rootd.exec.shutil.which", return_value=None):
        with pytest.raises(NftBinaryNotFoundError, match="not found on PATH"):
            nft_rule.find_nft_binary()


def test_find_nft_binary_raises_when_not_in_allowlist():
    """nft on PATH but at a path not in our exec allow-list."""
    with patch("hop3_rootd.exec.shutil.which", return_value="/opt/sketchy/nft"):
        with pytest.raises(NftBinaryNotFoundError, match="not found on PATH"):
            nft_rule.find_nft_binary()


def test_find_nft_binary_returns_allowlisted_path():
    with patch("hop3_rootd.exec.shutil.which", return_value="/usr/sbin/nft"):
        assert nft_rule.find_nft_binary() == "/usr/sbin/nft"


# --- build_add_argv -------------------------------------------------------


@pytest.fixture
def patched_nft():
    """Provide /usr/sbin/nft as the resolved binary."""
    with patch.object(nft_rule, "find_nft_binary", return_value="/usr/sbin/nft"):
        yield "/usr/sbin/nft"


def test_add_argv_simple_tcp_port(patched_nft):
    spec = PortSpec(
        protocol="tcp",
        app_name="matrix",
        source="any",
        port=8448,
    )
    argv = build_add_argv(spec, rule_id="abc-123")
    assert argv[0] == "/usr/sbin/nft"
    assert "add" in argv
    assert "rule" in argv
    assert TABLE_FAMILY in argv
    assert TABLE_NAME in argv
    assert CHAIN_NAME in argv
    assert "tcp" in argv
    assert "dport" in argv
    assert "8448" in argv
    assert "accept" in argv
    assert make_comment("abc-123") in argv
    # No saddr clause for source="any"
    assert "saddr" not in argv


def test_add_argv_udp(patched_nft):
    spec = PortSpec(
        protocol="udp",
        app_name="matrix-turn",
        source="any",
        port=3478,
    )
    argv = build_add_argv(spec, rule_id="def-456")
    assert "udp" in argv
    assert "3478" in argv
    assert "tcp" not in argv


def test_add_argv_port_range(patched_nft):
    spec = PortSpec(
        protocol="udp",
        app_name="matrix-turn",
        source="any",
        port_range=(49152, 65535),
    )
    argv = build_add_argv(spec, rule_id="ghi-789")
    assert "49152-65535" in argv


def test_add_argv_with_cidr_source(patched_nft):
    spec = PortSpec(
        protocol="tcp",
        app_name="db",
        source="10.0.0.0/8",
        port=5432,
    )
    argv = build_add_argv(spec, rule_id="jkl-012")
    # ip saddr <cidr> appears before the proto
    assert "ip" in argv
    assert "saddr" in argv
    assert "10.0.0.0/8" in argv
    # Order: ip saddr <cidr> tcp dport <port>
    ip_idx = argv.index("ip")
    proto_idx = argv.index("tcp")
    assert ip_idx < proto_idx


def test_add_argv_for_single_host_cidr(patched_nft):
    spec = PortSpec(
        protocol="tcp",
        app_name="ssh-restrict",
        source="192.168.1.42/32",
        port=22,
    )
    argv = build_add_argv(spec, rule_id="r1")
    assert "192.168.1.42/32" in argv


# --- build_delete_argv ----------------------------------------------------


def test_delete_argv(patched_nft):
    argv = build_delete_argv(handle=47)
    assert argv == [
        "/usr/sbin/nft",
        "delete",
        "rule",
        TABLE_FAMILY,
        TABLE_NAME,
        CHAIN_NAME,
        "handle",
        "47",
    ]


# --- run_nft --------------------------------------------------------------


def test_run_nft_returns_result_on_success():
    with patch.object(nft_rule, "exec_run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.success = True
        mock_run.return_value.stdout = "ok"
        mock_run.return_value.stderr = ""
        result = run_nft(["/usr/sbin/nft", "list", "ruleset"])
    assert result.success


def test_run_nft_raises_command_error_on_failure():
    with patch.object(nft_rule, "exec_run") as mock_run:
        mock_run.return_value.returncode = 1
        mock_run.return_value.success = False
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = "Error: something broke"
        with pytest.raises(NftCommandError) as e:
            run_nft(["/usr/sbin/nft", "list", "ruleset"])
        assert e.value.returncode == 1
        assert "something broke" in e.value.stderr


# --- parse_list_output ----------------------------------------------------


def test_parse_list_output_empty_table():
    """A table with chain but no rules → empty list."""
    obj = {
        "nftables": [
            {"metainfo": {}},
            {"table": {"family": "inet", "name": "hop3"}},
            {"chain": {"family": "inet", "table": "hop3", "name": "input"}},
        ]
    }
    assert parse_list_output(obj) == []


def test_parse_list_output_with_rules():
    """One rule with comment, one without."""
    obj = {
        "nftables": [
            {"table": {"family": "inet", "name": "hop3"}},
            {"chain": {"family": "inet", "name": "input"}},
            {
                "rule": {
                    "family": "inet",
                    "table": "hop3",
                    "chain": "input",
                    "handle": 4,
                    "expr": [],
                    "comment": "hop3:rule:abc-123",
                }
            },
            {
                "rule": {
                    "family": "inet",
                    "table": "hop3",
                    "chain": "input",
                    "handle": 7,
                    "expr": [],
                }
            },
        ]
    }
    rules = parse_list_output(obj)
    assert len(rules) == 2
    assert rules[0].handle == 4
    assert rules[0].comment == "hop3:rule:abc-123"
    assert rules[1].handle == 7
    assert rules[1].comment is None


def test_parse_list_output_skips_rules_without_handle():
    obj = {
        "nftables": [
            {"rule": {"family": "inet", "expr": []}},  # no handle
            {"rule": {"handle": 4, "expr": []}},
        ]
    }
    rules = parse_list_output(obj)
    assert len(rules) == 1
    assert rules[0].handle == 4


def test_parse_list_output_returns_kernel_rule():
    obj = {
        "nftables": [
            {"rule": {"handle": 4, "comment": "hop3:rule:r1", "expr": []}},
        ]
    }
    rules = parse_list_output(obj)
    assert isinstance(rules[0], KernelRule)
    assert rules[0].raw["handle"] == 4
