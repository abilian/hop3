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


def _app(
    *, port: int = 0, state: AppStateEnum = AppStateEnum.STOPPED
) -> SimpleNamespace:
    return SimpleNamespace(
        name="forgejo",
        runtime="uwsgi",
        src_path="/srv/forgejo",
        log_path=None,
        port=port,
        check_actual_status=lambda: state,
    )


def _abort_message(outcome: StartOutcome, timeout: float = 180.0) -> str:
    with pytest.raises(Abort) as exc:
        _handle_startup_failure(_app(), outcome, timeout)
    return str(exc.value)


def _bound_but_not_serving() -> SimpleNamespace:
    """The shape that cost three timeout bumps: socket bound, no worker."""
    return _app(port=8123, state=AppStateEnum.RUNNING)


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


def test_the_named_cause_reaches_the_abort_not_only_the_log():
    """
    The specific diagnosis used to be logged *below* the generic headline and
    below "Gathering diagnostic information...", so the operator read "failed
    to start within 240s" and raised the timeout — three times — while the
    answer sat underneath. It must travel with the verdict.
    """
    with pytest.raises(Abort) as exc:
        _handle_startup_failure(
            _bound_but_not_serving(), StartOutcome(started=False, elapsed=180.0), 180.0
        )

    message = str(exc.value)
    assert "8123" in message
    assert "no worker is serving" in message


def test_the_named_cause_is_recorded_where_the_dashboard_looks():
    """`error_message` is all the dashboard and `hop3 app status` show."""
    app = _bound_but_not_serving()

    with pytest.raises(Abort):
        _handle_startup_failure(app, StartOutcome(started=False, elapsed=180.0), 180.0)

    assert "no worker is serving" in app.error_message
    assert len(app.error_message) <= 1024  # the column's width


def test_a_failure_we_cannot_name_stays_generic():
    """No invented diagnosis when the state does not support one."""
    app = _app()

    with pytest.raises(Abort):
        _handle_startup_failure(app, StartOutcome(started=False, elapsed=180.0), 180.0)

    assert app.error_message == "App failed to start within 180.0s timeout"
