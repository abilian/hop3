# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the `addon exists` predicate (exit 0/1, silent, --json aware)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from hop3_cli.exit_codes import ExitCode
from hop3_cli.rpc.responses import _handle_predicate_response


@dataclass
class _StubPrinter:
    """Tracks print/flush calls via state, not mock assertions."""

    json_output: bool = False
    printed: bool = False
    flushed: bool = False

    def print(self, *args, **kwargs):
        self.printed = True

    def flush_json(self):
        self.flushed = True


def _printer(*, json_output=False):
    return _StubPrinter(json_output=json_output)


def test_exists_true_exits_zero_silently(capsys):
    printer = _printer()
    with pytest.raises(SystemExit) as exc:
        _handle_predicate_response([{"t": "data", "data": {"exists": True}}], printer)
    assert exc.value.code == ExitCode.SUCCESS
    assert not printer.printed  # silent in normal mode


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
    assert printer.printed
    assert printer.flushed


def test_no_payload_is_usage_error():
    printer = _printer()
    with pytest.raises(SystemExit) as exc:
        _handle_predicate_response([{"t": "error", "text": "Usage: ..."}], printer)
    assert exc.value.code == ExitCode.USAGE_ERROR
