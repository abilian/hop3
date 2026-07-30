# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
A command that reports a failure must exit non-zero.

A JSON-RPC `Ok` means "the server answered", not "the operation worked".
Commands signal a command-level failure by returning an `error` element in an
otherwise successful response — and nothing turned that into an exit code, so
they printed the failure in red and exited 0.

The cost was not theoretical. `hop3 app check` reports a failed smoke test that
way, and the catalog driver — which trusts the exit code, as any script would —
recorded **PASS for three applications whose checks had just failed**, on the
run whose "20/20" figure was about to go into a report. The output said one
thing and the exit code said the opposite; the exit code is what automation
reads.
"""

from __future__ import annotations

import pytest
from hop3_cli.rpc.responses import _reports_failure, handle_response
from jsonrpcclient import Ok


class _Printer:
    """Records what was printed; never fails."""

    json_output = False
    verbose = False

    def __init__(self) -> None:
        self.printed: list[list[dict]] = []

    def print(self, result) -> None:
        self.printed.append(result)

    def flush_json(self) -> None:
        pass


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ([{"t": "error", "text": "Smoke test FAILED for 'isso'."}], True),
        ([{"t": "text", "text": "ok"}, {"t": "error", "text": "boom"}], True),
        ([{"t": "text", "text": "Smoke test passed."}], False),
        ([{"t": "warning", "text": "a warning is not a failure"}], False),
        ([], False),
        (None, False),
    ],
)
def test_which_responses_report_a_failure(result, expected: bool) -> None:
    assert _reports_failure(result) is expected


def test_an_error_element_exits_non_zero() -> None:
    """The regression: this printed the error and exited 0."""
    printer = _Printer()

    with pytest.raises(SystemExit) as excinfo:
        handle_response(
            Ok(result=[{"t": "error", "text": "Smoke test FAILED for 'isso'."}], id=1),
            ["app", "check", "--app", "isso"],
            None,
            printer,
        )

    assert excinfo.value.code != 0, (
        "a reported failure must be visible to a script, not only to a human"
    )
    # The operator still gets the message: exiting must not swallow the output.
    assert printer.printed, "the error was not printed before exiting"


def test_a_successful_response_still_exits_zero() -> None:
    """The fix must not turn ordinary output into a failure."""
    printer = _Printer()

    handle_response(
        Ok(result=[{"t": "text", "text": "Smoke test passed for 'radicale'."}], id=1),
        ["app", "check", "--app", "radicale"],
        None,
        printer,
    )

    assert printer.printed
