# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for ADR 036 D16 exit codes."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from hop3_cli.exit_codes import (
    ExitCode,
    map_message_to_exit,
    map_rpc_code_to_exit,
)
from hop3_cli.main import main
from hop3_cli.rpc.responses import handle_error_response

# ---- D16 numbering is locked ----


def test_d16_numbering() -> None:
    """The D16 table is part of the public CLI contract — pin the values."""
    assert ExitCode.SUCCESS == 0
    assert ExitCode.GENERAL_ERROR == 1
    assert ExitCode.USAGE_ERROR == 2
    assert ExitCode.RESOLUTION_ERROR == 3
    assert ExitCode.AUTH_ERROR == 4
    assert ExitCode.AUTHZ_ERROR == 5
    assert ExitCode.CONFLICT_ERROR == 6
    assert ExitCode.NETWORK_ERROR == 7
    assert ExitCode.DEPLOYMENT_ERROR == 8
    assert ExitCode.PLUGIN_ERROR == 9
    assert ExitCode.CONFIRMATION_DECLINED == 10
    assert ExitCode.INTERRUPTED == 130


def test_back_compat_aliases_point_at_d16_codes() -> None:
    """Old names left as aliases must point at the D16 numbers, not their old values."""
    assert ExitCode.NOT_FOUND == ExitCode.RESOLUTION_ERROR == 3
    assert ExitCode.VALIDATION_ERROR == ExitCode.USAGE_ERROR == 2
    assert ExitCode.SERVER_ERROR == ExitCode.NETWORK_ERROR == 7
    assert ExitCode.CONNECTION_ERROR == ExitCode.NETWORK_ERROR == 7
    assert ExitCode.TIMEOUT_ERROR == ExitCode.NETWORK_ERROR == 7


# ---- map_rpc_code_to_exit ----


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (401, ExitCode.AUTH_ERROR),
        (403, ExitCode.AUTHZ_ERROR),
        (404, ExitCode.RESOLUTION_ERROR),
        (409, ExitCode.CONFLICT_ERROR),
        (413, ExitCode.USAGE_ERROR),  # payload too large
        (500, ExitCode.NETWORK_ERROR),
        (-32601, ExitCode.RESOLUTION_ERROR),  # method not found
        (-32602, ExitCode.USAGE_ERROR),  # invalid params
        (-32603, ExitCode.NETWORK_ERROR),  # internal error
    ],
)
def test_rpc_code_mapping(code: int, expected: int) -> None:
    assert map_rpc_code_to_exit(code) == expected


def test_unknown_rpc_code_falls_back_to_general_error() -> None:
    assert map_rpc_code_to_exit(999) == ExitCode.GENERAL_ERROR


# ---- map_message_to_exit ----


@pytest.mark.parametrize(
    ("msg", "expected"),
    [
        ("App 'foo' not found", ExitCode.RESOLUTION_ERROR),
        ("Database does not exist", ExitCode.RESOLUTION_ERROR),
        ("Permission denied", ExitCode.AUTHZ_ERROR),
        ("Operation forbidden", ExitCode.AUTHZ_ERROR),
        ("Authentication failed", ExitCode.AUTH_ERROR),
        ("Unauthorized request", ExitCode.AUTH_ERROR),
        ("App 'foo' already exists", ExitCode.CONFLICT_ERROR),
        ("Conflict: resource locked", ExitCode.CONFLICT_ERROR),
        ("Deployment failed: build error", ExitCode.DEPLOYMENT_ERROR),
        ("Connection refused", ExitCode.NETWORK_ERROR),
        ("Operation timed out", ExitCode.NETWORK_ERROR),
        ("Invalid argument", ExitCode.USAGE_ERROR),
        ("Validation error: missing field", ExitCode.USAGE_ERROR),
        ("Usage: hop3 deploy <app>", ExitCode.USAGE_ERROR),
        ("Something completely unexpected", ExitCode.GENERAL_ERROR),
    ],
)
def test_message_mapping(msg: str, expected: int) -> None:
    assert map_message_to_exit(msg) == expected


# ---- SIGINT handler ----


def test_keyboard_interrupt_in_main_exits_130() -> None:
    """Ctrl-C anywhere in the run path becomes exit code 130 (D16)."""
    with (
        patch("hop3_cli.main.run_command_from_args", side_effect=KeyboardInterrupt),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()
    assert exc_info.value.code == 130


# ---- 413 deploy diagnostic ----


def test_413_replaces_raw_http_error_with_actionable_diagnostic(capsys) -> None:
    """A 413 must yield a remediation message, not the raw HTTP error."""
    with pytest.raises(SystemExit) as exc:
        handle_error_response(
            413, "HTTP 413 error: 413 Client Error: Payload Too Large for url: ..."
        )
    assert exc.value.code == ExitCode.USAGE_ERROR

    out = capsys.readouterr()
    combined = out.out + out.err
    assert "too large" in combined.lower()
    assert "[build].ignore" in combined
    # The raw HTTP noise is not what the user sees.
    assert "Client Error: Payload Too Large for url" not in combined
