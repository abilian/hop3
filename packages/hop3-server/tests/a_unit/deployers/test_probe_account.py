# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
The Hop3-owned probe account ([probe]).

The [admin] credential is handed to the operator, so a later sign-in failure
could equally mean the app broke or its password moved — indistinguishable from
outside. Nobody else uses the probe account, so a refused probe sign-in means
the app broke.
"""

from __future__ import annotations

import pytest

from hop3.core.env import Env
from hop3.deployers.probe_account import (
    DEFAULT_USERNAME,
    bootstrap_probe_account,
    provision_probe_credential,
)


class _App:
    def __init__(self, env: dict | None = None) -> None:
        self.name = "myapp"
        self._env = dict(env or {})

    def get_runtime_env(self) -> Env:
        return Env(dict(self._env))


@pytest.fixture
def captured(monkeypatch) -> dict:
    """Capture what would be written to the app's env."""
    written: dict = {}

    def _set_env_vars(app, values, session):
        written.update(values)

    monkeypatch.setattr("hop3.deployers.probe_account.set_env_vars", _set_env_vars)
    return written


def test_no_probe_section_provisions_nothing(captured) -> None:
    """An app may opt out; it then verifies the handover only."""
    provision_probe_credential(_App(), {}, object())

    assert captured == {}


def test_a_password_is_generated_and_injected(captured) -> None:
    provision_probe_credential(_App(), {"username": "hop3probe"}, object())

    assert captured["HOP3_PROBE_USER"] == "hop3probe"
    assert len(captured["HOP3_PROBE_PASSWORD"]) >= 16


def test_the_password_is_stable_across_deploys(captured) -> None:
    """
    ADR 046: a secret regenerated per deploy would break the account it created.

    The probe's password may be ROTATED deliberately, but never by accident.
    """
    app = _App({"HOP3_PROBE_PASSWORD": "already-minted"})

    provision_probe_credential(app, {"username": "hop3probe"}, object())

    assert captured["HOP3_PROBE_PASSWORD"] == "already-minted"


def test_the_username_defaults(captured) -> None:
    provision_probe_credential(_App(), {"email": "p@example.invalid"}, object())

    assert captured["HOP3_PROBE_USER"] == DEFAULT_USERNAME


def test_create_runs_once(captured) -> None:
    """A redeploy must not re-run creation; the command is guarded."""
    calls: list[str] = []
    probe = {"username": "hop3probe", "create": "make-user"}

    bootstrap_probe_account(_App(), probe, object(), calls.append)
    assert calls == ["make-user"]
    assert captured["HOP3_PROBE_CREATED"] == "1"

    already = _App({"HOP3_PROBE_CREATED": "1"})
    calls.clear()
    bootstrap_probe_account(already, probe, object(), calls.append)
    assert calls == []


def test_a_failed_create_is_loud_but_does_not_fail_the_deploy(captured) -> None:
    """
    The probe verifies the app; it is not part of it.

    Aborting here would take a working app down because a TEST account could
    not be created — making the platform's diagnostics a deployment
    dependency. Nothing is silently skipped: the smoke test then falls back to
    the operator's credential and reports that it did.
    """

    def _boom(command: str) -> None:
        msg = "exit status 1"
        raise RuntimeError(msg)

    bootstrap_probe_account(
        _App(), {"username": "p", "create": "make-user"}, object(), _boom
    )

    # Not marked as created, so a later deploy retries rather than assuming.
    assert "HOP3_PROBE_CREATED" not in captured


def test_an_app_that_self_bootstraps_needs_no_create_command(captured) -> None:
    """
    No `[probe].create` means the APP makes the account from the injected vars.

    Hop3 runs nothing here and, crucially, claims nothing either. Marking such
    a probe as created — so the smoke test would sign in as it — was tried and
    reverted the same day: matomo went from PASS to FAIL in one run and
    uptime-kuma kept failing, both against accounts their own bootstraps were
    supposed to have created. The check falls back to the operator's credential
    and reports the weaker claim, which is accurate rather than silent.
    """
    calls: list[str] = []

    bootstrap_probe_account(_App(), {"username": "p"}, object(), calls.append)

    assert calls == [], "there is no command to run on this path"
    assert "HOP3_PROBE_CREATED" not in captured, (
        "Hop3 did not create this account and cannot see whether anyone did, so "
        "it must not mark one as existing — marking it took matomo from PASS to "
        "FAIL and left uptime-kuma failing on an account nobody had made"
    )


# --- [probe].verify: exit 0 from `create` is not evidence -------------------


def test_verify_failure_does_not_mark_the_account_created(captured):
    """
    The marker means "this account exists".

    `create` exiting 0 is the app CLI's claim, not proof: Gitea and Forgejo
    print an error and still exit 0 for the reserved name 'admin'. When a
    declared `verify` fails, the claim is known false, so the marker must not
    be written — otherwise the smoke test signs in as an absent account and
    blames the app.
    """
    ran: list[str] = []

    def run_create(command: str) -> None:
        ran.append(command)
        if command == "verify-cmd":
            msg = "no such user"
            raise RuntimeError(msg)

    bootstrap_probe_account(
        _App(),
        {"username": "hop3probe", "create": "create-cmd", "verify": "verify-cmd"},
        db_session=None,
        run_create=run_create,
    )

    assert ran == ["create-cmd", "verify-cmd"]
    assert captured == {}, "marker written despite verification failing"


def test_verify_success_marks_the_account_created(captured):
    bootstrap_probe_account(
        _App(),
        {"username": "hop3probe", "create": "create-cmd", "verify": "verify-cmd"},
        db_session=None,
        run_create=lambda command: None,
    )

    assert captured, "marker not written after create and verify both succeeded"


def test_without_verify_the_old_behaviour_is_kept(captured):
    # Recipes that predate `verify` keep working; the log says it is unverified.
    bootstrap_probe_account(
        _App(),
        {"username": "hop3probe", "create": "create-cmd"},
        db_session=None,
        run_create=lambda command: None,
    )

    assert captured
