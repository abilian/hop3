# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
`hop3 run` must surface the failed command's output, not just the exit code.

Many scripts write their progress and tracebacks to stdout; if RunCmd only
relayed stderr, a failing command showed a bare "exit code 1" with no detail.

These guarantees predate streaming and outlive it. What changed is where the
output appears: it is written to the stream as it arrives rather than
returned in a block at the end, so the assertions read the stream.
"""

from __future__ import annotations

import sys
import time
from typing import TYPE_CHECKING

import pytest

from hop3.commands import misc
from hop3.server.streaming import get_stream

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from hop3.orm import App


def run_and_wait(db_session: Session, *args: str, timeout: float = 10.0):
    """Call RunCmd and return the stream once its command has finished."""
    result = misc.RunCmd(db_session=db_session).call(*args)
    assert result[0]["t"] == "stream", result
    stream = get_stream(result[0]["stream_id"])
    assert stream is not None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if stream.complete:
            return stream
        time.sleep(0.02)
    pytest.fail("the command never finished")
    return None


def output_of(stream) -> str:
    return "\n".join(entry.msg for entry in stream.logs)


def test_run_surfaces_stdout_on_failure(db_session: Session, test_app: App) -> None:
    script = "print('Importing annuaire...'); raise ValueError('boom')"
    stream = run_and_wait(db_session, "--app", "testapp", sys.executable, "-c", script)

    assert stream.success is False
    out = output_of(stream)
    assert "Importing annuaire..." in out, "stdout is surfaced, not dropped"
    assert "Traceback" in out
    assert "ValueError: boom" in out


def test_run_includes_both_streams_on_failure(
    db_session: Session, test_app: App
) -> None:
    """
    Both streams reach the operator. They are interleaved now rather than
    shown one after the other, because while output is arriving live the
    order the program printed in is the information.
    """
    script = (
        "import sys; print('stdout line'); "
        "print('stderr line', file=sys.stderr); "
        "raise SystemExit(2)"
    )
    stream = run_and_wait(db_session, "--app", "testapp", sys.executable, "-c", script)

    out = output_of(stream)
    assert "stdout line" in out
    assert "stderr line" in out
    assert "exit code 2" in stream.error_message


def test_run_says_so_when_no_output_was_captured(
    db_session: Session, test_app: App
) -> None:
    """A failure with empty streams must not be a silent bare exit code."""
    stream = run_and_wait(
        db_session, "--app", "testapp", sys.executable, "-c", "raise SystemExit(1)"
    )

    out = output_of(stream)
    assert "exit code 1" in stream.error_message
    assert f"$ {sys.executable}" in out, "the exact command is echoed"
    assert "no output" in out, "explicit, not a silent bare code"


def test_run_echoes_the_command_before_it_starts(
    db_session: Session, test_app: App
) -> None:
    """So a job that is slow to print is still visibly under way."""
    stream = run_and_wait(
        db_session, "--app", "testapp", sys.executable, "-c", "print('hi')"
    )
    assert next(iter(stream.logs)).msg.startswith("$ ")
    assert stream.success is True
