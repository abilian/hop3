# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
A failed startup must say what actually happened.

The wait gives up for two unrelated reasons: the deadline elapsed, or the app
crashed on every respawn and waiting became pointless. Both used to return a
bare ``False``, so both were reported as a timeout — forgejo failed in 11
seconds and the operator was told it "did not respond to health checks within
180.0s", then advised to raise the timeout, the one change that could not help.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from hop3.deployers.deployer import StartOutcome, _handle_startup_failure
from hop3.lib.console import Abort
from hop3.orm import AppStateEnum


def _app() -> SimpleNamespace:
    return SimpleNamespace(
        name="forgejo",
        runtime="uwsgi",
        src_path="/srv/forgejo",
        log_path=None,
        port=0,
        check_actual_status=lambda: AppStateEnum.STOPPED,
    )


def _abort_message(outcome: StartOutcome, timeout: float = 180.0) -> str:
    with pytest.raises(Abort) as exc:
        _handle_startup_failure(_app(), outcome, timeout)
    return str(exc.value)


def test_a_crash_loop_is_not_reported_as_a_timeout():
    message = _abort_message(StartOutcome(started=False, crash_looped=True, elapsed=11))
    assert "crashed repeatedly" in message
    assert "did not respond to health checks within" not in message


def test_a_crash_loop_says_the_timeout_was_never_reached():
    """
    Naming the elapsed time and the unreached deadline together stops the
    reader from assuming a slow app.
    """
    message = _abort_message(StartOutcome(started=False, crash_looped=True, elapsed=11))
    assert "11s" in message
    assert "never reached" in message


def test_a_crash_loop_does_not_advise_raising_the_timeout():
    message = _abort_message(StartOutcome(started=False, crash_looped=True, elapsed=11))
    assert "start-timeout" not in message


def test_a_real_timeout_still_reads_as_one_and_keeps_the_remedy():
    message = _abort_message(StartOutcome(started=False, elapsed=180.0))
    assert "did not respond to health checks within 180.0s" in message
    assert "start-timeout = 360" in message


def test_the_recorded_error_matches_the_verdict():
    app = _app()
    with pytest.raises(Abort):
        _handle_startup_failure(
            app, StartOutcome(started=False, crash_looped=True, elapsed=11), 180.0
        )
    assert "crashed repeatedly" in app.error_message
    assert "180" not in app.error_message
