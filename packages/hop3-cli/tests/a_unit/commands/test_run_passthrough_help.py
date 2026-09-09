# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
`--help` after a `run` program belongs to the program, not to hop3.

`hop3 run annuaire-cli maintenance daily --help` printed the help for `hop3 run`
and the program never saw the flag: `handle_help_flags` searched the whole of
argv, while `parse_flags` had always stopped consuming global flags at the
program token. Two passes over the same argv, one boundary, only one of them
knew about it.
"""

from __future__ import annotations

import pytest
from hop3_cli.commands.flags import parse_flags
from hop3_cli.commands.help import handle_help_flags
from hop3_cli.core.app_scope import run_passthrough_index


class TestBoundary:
    @pytest.mark.parametrize(
        ("args", "expected"),
        [
            (["run", "cli", "sub", "--help"], 2),  # `cli` is the program
            (["run", "--help"], 2),  # no program: all ours
            (["app", "run", "cli", "--help"], 3),  # the canonical spelling
            (["run", "--input", "data", "cli", "--help"], 4),  # --input's value
            (["apps", "--help"], 2),  # not a run command
            (["status"], 1),
            ([], 0),
        ],
    )
    def test_index(self, args, expected):
        assert run_passthrough_index(args) == expected

    def test_agrees_with_parse_flags(self):
        """
        The boundary must be the one `parse_flags` enforces.

        It stops consuming global flags at the program, so `--json` after it is
        the program's. If the two disagreed, one pass would read a token the
        other had handed away.
        """
        flags, rest = parse_flags(["run", "cli", "--json"])
        assert flags.json_output is False, "--json after the program is not ours"
        assert rest == ["run", "cli", "--json"]
        assert run_passthrough_index(rest) == 2


class TestHelpIsNotStolen:
    def test_the_reported_case(self):
        args = ["run", "annuaire-cli", "maintenance", "daily", "--help"]
        assert handle_help_flags(list(args)) == args

    def test_canonical_app_run_too(self):
        args = ["app", "run", "cli", "sub", "--help"]
        assert handle_help_flags(list(args)) == args

    def test_short_form_too(self):
        args = ["run", "cli", "-h"]
        assert handle_help_flags(list(args)) == args

    def test_version_is_not_stolen_either(self):
        args = ["run", "cli", "--version"]
        assert handle_help_flags(list(args)) == args

    def test_input_value_is_not_mistaken_for_the_program(self):
        args = ["run", "--input", "data", "cli", "--help"]
        assert handle_help_flags(list(args)) == args


class TestHelpStillWorks:
    @pytest.mark.parametrize(
        ("args", "expected"),
        [
            (["--help"], ["help"]),
            (["-h"], ["help"]),
            (["run", "--help"], ["help", "run"]),  # run's own help, no program
            (["app", "run", "--help"], ["help", "app", "run"]),
            (["apps", "--help"], ["help", "apps"]),
            (["config", "show", "--help"], ["help", "config", "show"]),
            (["--version"], ["version"]),
            (["-V"], ["version"]),
        ],
    )
    def test_unchanged(self, args, expected):
        assert handle_help_flags(list(args)) == expected

    def test_no_help_flag_passes_through(self):
        assert handle_help_flags(["apps"]) == ["apps"]
