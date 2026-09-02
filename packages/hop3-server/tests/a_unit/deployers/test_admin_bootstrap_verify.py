# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
`[admin].create` exiting 0 is not evidence the account was created.

Gitea and Forgejo reject the reserved name 'admin' by printing an error and
exiting 0. Hop3 trusted that exit code, set ``bootstrapped = True`` and handed
the operator a password for an account that had never been made — a running app
they could not log into, reported as a successful deploy.

``[admin].verify`` is the evidence. When declared it must succeed before the
credential is marked bootstrapped.
"""

from __future__ import annotations

import pytest

from hop3.deployers.admin_bootstrap import AdminBootstrapError, bootstrap_admin_account


class _Credential:
    def __init__(self) -> None:
        self.bootstrapped = False


class _Repo:
    def __init__(self, credential) -> None:
        self._credential = credential

    def get_by_app_id(self, app_id):
        return self._credential


class _Session:
    def __init__(self) -> None:
        self.committed = False

    def add(self, obj) -> None:
        pass

    def commit(self) -> None:
        self.committed = True


class _App:
    name = "myapp"
    id = 1


@pytest.fixture
def credential(monkeypatch):
    cred = _Credential()
    monkeypatch.setattr(
        "hop3.deployers.admin_bootstrap.AppAdminCredentialRepository",
        lambda session: _Repo(cred),
    )
    return cred


def test_verify_failure_aborts_and_leaves_the_credential_unbootstrapped(credential):
    session = _Session()

    def run_create(command: str) -> None:
        if command == "verify-cmd":
            msg = "user 'admin' does not exist"
            raise RuntimeError(msg)

    with pytest.raises(AdminBootstrapError, match="could not be verified"):
        bootstrap_admin_account(
            _App(),
            {"create": "create-cmd", "verify": "verify-cmd"},
            session,
            run_create,
        )

    assert not credential.bootstrapped, "marked bootstrapped despite failed verify"
    assert not session.committed


def test_verify_success_marks_bootstrapped(credential):
    session = _Session()

    bootstrap_admin_account(
        _App(),
        {"create": "create-cmd", "verify": "verify-cmd"},
        session,
        lambda command: None,
    )

    assert credential.bootstrapped
    assert session.committed


def test_verify_runs_after_create(credential):
    order: list[str] = []

    bootstrap_admin_account(
        _App(),
        {"create": "create-cmd", "verify": "verify-cmd"},
        _Session(),
        order.append,
    )

    assert order == ["create-cmd", "verify-cmd"]


def test_recipes_without_verify_still_work(credential):
    # Backwards compatible: no verify declared, behaviour unchanged.
    session = _Session()

    bootstrap_admin_account(
        _App(), {"create": "create-cmd"}, session, lambda command: None
    )

    assert credential.bootstrapped
    assert session.committed
