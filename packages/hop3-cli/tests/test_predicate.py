# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the `addon exists` predicate (exit 0/1, silent, --json aware)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from hop3_cli.exit_codes import ExitCode
from hop3_cli.rpc.responses import _handle_predicate_response


def _printer(*, json_output=False):
    p = MagicMock()
    p.json_output = json_output
    return p


def test_exists_true_exits_zero_silently(capsys):
    printer = _printer()
    with pytest.raises(SystemExit) as exc:
        _handle_predicate_response([{"t": "data", "data": {"exists": True}}], printer)
    assert exc.value.code == ExitCode.SUCCESS
    printer.print.assert_not_called()  # silent in normal mode


def test_exists_false_exits_one(capsys):
    printer = _printer()
    with pytest.raises(SystemExit) as exc:
        _handle_predicate_response([{"t": "data", "data": {"exists": False}}], printer)
    assert exc.value.code == 1


def test_json_mode_emits_payload_and_exits():
    printer = _printer(json_output=True)
    with pytest.raises(SystemExit) as exc:
        _handle_predicate_response([{"t": "data", "data": {"exists": True}}], printer)
    assert exc.value.code == ExitCode.SUCCESS
    printer.print.assert_called_once()
    printer.flush_json.assert_called_once()


def test_no_payload_is_usage_error():
    printer = _printer()
    with pytest.raises(SystemExit) as exc:
        _handle_predicate_response([{"t": "error", "text": "Usage: ..."}], printer)
    assert exc.value.code == ExitCode.USAGE_ERROR
