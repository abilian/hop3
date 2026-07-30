# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
The shared smoke-test runner, used by `hop3 app check` and by every deploy.

Deploying proves an app STARTS. Running its check.py proves it WORKS — the
distinction that mattered repeatedly: apps served their login page perfectly
while rejecting every credential.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from hop3.core.env import Env
from hop3.server.checks.runner import CHECK_TIMEOUT, run_app_check


def _app(tmp_path, script: str | None):
    src = tmp_path / "src"
    src.mkdir()
    if script is not None:
        (src / "check.py").write_text(script)
    return SimpleNamespace(
        name="myapp",
        src_path=src,
        get_runtime_env=lambda: Env({"HOST_NAME": "myapp.example.com"}),
    )


@pytest.fixture
def no_credential(monkeypatch):
    monkeypatch.setattr(
        "hop3.server.checks.runner.read_admin_credential", lambda app, session: None
    )


def test_an_app_without_a_check_did_not_fail(tmp_path, no_credential) -> None:
    """
    No check.py is not a failed test — it is no test.

    Reporting it as a pass would claim verification that never happened.
    """
    outcome = run_app_check(_app(tmp_path, None), object())

    assert outcome.ran is False
    assert outcome.passed is True
    assert "nothing was verified" in outcome.summary


def test_a_passing_check_reports_its_output(tmp_path, no_credential) -> None:
    outcome = run_app_check(_app(tmp_path, "print('all good')"), object())

    assert outcome.ran is True
    assert outcome.passed is True
    assert "all good" in outcome.output


def test_a_failing_check_is_reported_as_failed(tmp_path, no_credential) -> None:
    script = "import sys; print('bad password'); sys.exit(1)"

    outcome = run_app_check(_app(tmp_path, script), object())

    assert outcome.ran is True
    assert outcome.passed is False
    assert "bad password" in outcome.output
    assert "FAILED" in outcome.summary


def test_the_credential_reaches_the_check(tmp_path, monkeypatch) -> None:
    """The check must sign in with what `hop3 app credentials` would show."""
    monkeypatch.setattr(
        "hop3.server.checks.runner.read_admin_credential",
        lambda app, session: {
            "username": "admin",
            "email": "ops@example.com",
            "password": "s3cret",
        },
    )
    script = (
        "import os, sys\n"
        "assert os.environ['HOP3_ADMIN_USER'] == 'admin'\n"
        "assert os.environ['HOP3_ADMIN_PASSWORD'] == 's3cret'\n"
        "print('credential received')\n"
    )

    outcome = run_app_check(_app(tmp_path, script), object())

    assert outcome.passed is True, outcome.output


def test_a_hung_check_fails_rather_than_hanging_the_caller(
    tmp_path, no_credential, monkeypatch
) -> None:
    """
    A check that never returns is a failure, not a wait.

    Whatever it was waiting for never arrived — precisely what it exists to
    detect — and neither an RPC call nor a deploy may block on it forever.
    """
    monkeypatch.setattr("hop3.server.checks.runner.CHECK_TIMEOUT", 1)
    outcome = run_app_check(_app(tmp_path, "import time; time.sleep(30)"), object())

    assert outcome.ran is True
    assert outcome.passed is False
    assert "did not finish" in outcome.output


def test_the_timeout_is_bounded() -> None:
    assert 0 < CHECK_TIMEOUT <= 600


def test_a_pass_without_a_probe_is_reported_as_the_weaker_claim(
    tmp_path, no_credential, monkeypatch
) -> None:
    """
    Signing in as the OPERATOR's credential verifies the handover, not more.

    That credential stops being Hop3's to assert once they change the password,
    so a green result there must not read the same as one from an account Hop3
    still owns.
    """
    monkeypatch.delenv("HOP3_PROBE_PASSWORD", raising=False)

    outcome = run_app_check(_app(tmp_path, "print('ok')"), object())

    assert outcome.passed is True
    assert outcome.used_hop3_account is False
    assert "handover only" in outcome.summary


def test_a_pass_with_a_probe_is_the_full_claim(
    tmp_path, no_credential, monkeypatch
) -> None:
    """An app with a CREATED [probe] is verified with an account only Hop3 uses."""
    monkeypatch.setenv("HOP3_PROBE_PASSWORD", "hop3-owned")
    monkeypatch.setenv("HOP3_PROBE_CREATED", "1")

    outcome = run_app_check(_app(tmp_path, "print('ok')"), object())

    assert outcome.passed is True
    assert outcome.used_hop3_account is True
    assert outcome.summary == "smoke test passed"


def test_a_probe_that_was_never_created_is_not_offered_to_the_check(
    tmp_path, no_credential, monkeypatch
) -> None:
    """
    Regression: a failed probe bootstrap left the credential in the env.

    `HOP3_PROBE_*` is injected so the recipe's own `create` command can make the
    account. When that command failed the variables stayed, `Check.has_probe`
    kept reporting a probe was available, and the check signed in as an account
    nobody had created — then reported the APPLICATION broken. Mattermost hit
    exactly this: its `mmctl --local` socket is not enabled, the probe was never
    created, and a perfectly working app failed its own smoke test.

    Without `HOP3_PROBE_CREATED`, the check must not see a probe at all.
    """
    monkeypatch.setenv("HOP3_PROBE_PASSWORD", "never-created")
    monkeypatch.setenv("HOP3_PROBE_USER", "hop3probe")
    monkeypatch.delenv("HOP3_PROBE_CREATED", raising=False)

    # The script fails if it can see a probe credential, so a pass proves the
    # variables were withheld.
    script = (
        "import os, sys\nsys.exit(1 if os.environ.get('HOP3_PROBE_PASSWORD') else 0)\n"
    )
    outcome = run_app_check(_app(tmp_path, script), object())

    assert outcome.passed is True, "the check could still see the probe credential"
    assert outcome.used_hop3_account is False, (
        "a probe that was never created must not be claimed as one Hop3 owns"
    )
    assert "handover only" in outcome.summary
