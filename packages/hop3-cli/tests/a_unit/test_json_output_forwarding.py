# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
`--json` is the client's own flag, so a command with a structured answer is told.

`hop3 system status --json` was documented, and advertised, as the health report
in machine form. The client consumed `--json` as its output switch, the command
never saw it, and the "JSON" was the rich text report wrapped in a list.
"""

from __future__ import annotations

import pytest
from hop3_cli.commands.arguments import get_extra_args


@pytest.mark.parametrize("argv", [["system", "status"], ["help", "--all"]])
def test_a_command_with_a_data_answer_is_told_json_was_asked(argv):
    assert get_extra_args(argv, json_output=True)["json_output"] is True


def test_not_without_json():
    assert "json_output" not in get_extra_args(["system", "status"])


@pytest.mark.parametrize("argv", [["postgres", "list"], ["system", "info"]])
def test_not_to_a_command_that_takes_no_such_argument(argv):
    """An older server hands every extra argument to the command's `call`."""
    assert "json_output" not in get_extra_args(argv, json_output=True)
