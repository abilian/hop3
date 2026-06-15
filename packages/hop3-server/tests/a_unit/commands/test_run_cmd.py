# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""`hop3 run` must surface the failed command's output, not just the exit code.

Many scripts write their progress and tracebacks to stdout; if RunCmd only
relayed stderr, a failing command showed a bare "exit code 1" with no detail.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.commands import misc
from hop3.lib.util import CommandFailedError

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from hop3.orm import App


def _text_of(result) -> str:
    return "\n".join(r.get("text", "") for r in result)


def test_run_surfaces_stdout_on_failure(
    db_session: Session, test_app: App, monkeypatch
) -> None:
    def fake_run_command(*_args, **_kwargs):
        raise CommandFailedError(
            ["python", "script.py"],
            returncode=1,
            stderr="",
            stdout="Importing annuaire...\nTraceback (most recent call last):\nValueError: boom",
        )

    monkeypatch.setattr(misc, "run_command", fake_run_command)

    result = misc.RunCmd(db_session=db_session).call("testapp", "python", "script.py")

    out = _text_of(result)
    assert "exit code 1" in out
    assert "ValueError: boom" in out  # stdout is surfaced, not dropped
    assert "Traceback" in out


def test_run_includes_both_streams_on_failure(
    db_session: Session, test_app: App, monkeypatch
) -> None:
    def fake_run_command(*_args, **_kwargs):
        raise CommandFailedError(
            ["cmd"], returncode=2, stderr="stderr line", stdout="stdout line"
        )

    monkeypatch.setattr(misc, "run_command", fake_run_command)

    out = _text_of(misc.RunCmd(db_session=db_session).call("testapp", "cmd"))
    assert "stdout line" in out
    assert "stderr line" in out
    assert "--- stderr ---" in out
