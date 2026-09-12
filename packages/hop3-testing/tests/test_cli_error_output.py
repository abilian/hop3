# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
An expected refusal prints its sentence, not a stack trace.

`hop3-test run --provider hetzner` against an unlabelled server answered with
twenty frames of click internals and then the one line that mattered:

    refusing to rebuild server 115746898 (hop3-dev): it is not labelled
    hop3-throwaway=true. Rebuilds wipe the box; label the dedicated test
    server once with `hcloud server add-label ...`

The guard was right to refuse — that label is what stops a rebuild wiping a
box someone uses. Being right is the point: a traceback says "this program
broke", and nothing here broke.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from hop3_testing.cli import main

# Aliased: pytest tries to collect anything named Test* as a test class.
from hop3_testing.exceptions import DeploymentError, TestingError as HarnessError
from hop3_testing.system_tests.hetzner import HetznerError, ServerResetError

REFUSAL = "refusing to rebuild server 115746898: it is not labelled hop3-throwaway"


def run_main(error: BaseException, argv: list[str]):
    with (
        patch("hop3_testing.cli.cli", side_effect=error),
        patch("sys.argv", argv),
        pytest.raises(SystemExit) as exit_info,
    ):
        main()
    return exit_info.value


class TestAnExpectedFailurePrintsItsMessage:
    def test_the_message_is_shown_without_a_traceback(self, capsys) -> None:
        run_main(ServerResetError(REFUSAL), ["hop3-test", "run"])
        err = capsys.readouterr().err
        assert REFUSAL in err
        assert "Traceback" not in err
        assert "click/core.py" not in err

    def test_it_exits_non_zero(self) -> None:
        assert run_main(ServerResetError(REFUSAL), ["hop3-test", "run"]).code == 1

    @pytest.mark.parametrize(
        "error",
        [
            ServerResetError("refused"),
            DeploymentError("the deploy failed"),
            HarnessError("something the harness knows about"),
        ],
    )
    def test_every_error_the_package_defines_is_covered(self, error, capsys) -> None:
        run_main(error, ["hop3-test", "run"])
        assert str(error) in capsys.readouterr().err

    def test_hetzner_errors_are_part_of_the_package_hierarchy(self) -> None:
        """They were a separate tree, so the CLI handler could not see them."""
        assert issubclass(HetznerError, HarnessError)


class TestABugStillShowsItsTraceback:
    def test_an_unexpected_error_propagates(self) -> None:
        """The frames are the report when the program genuinely broke."""
        boom = RuntimeError("index out of range")
        with (
            patch("hop3_testing.cli.cli", side_effect=boom),
            patch("sys.argv", ["hop3-test", "run"]),
            pytest.raises(RuntimeError, match="index out of range"),
        ):
            main()

    @pytest.mark.parametrize("flag", ["-v", "--verbose"])
    def test_verbose_brings_the_traceback_back(self, flag) -> None:
        """For when the question is where it was raised, not what it said."""
        with (
            patch("hop3_testing.cli.cli", side_effect=ServerResetError(REFUSAL)),
            patch("sys.argv", ["hop3-test", flag, "run"]),
            pytest.raises(ServerResetError),
        ):
            main()
