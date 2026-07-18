# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the verifier's pure logic (no network)."""

from __future__ import annotations

from hop3_tooling.credentials import Credential
from hop3_tooling.verify import CHECKS, _hidden_input, resolve_login_id


def _cred() -> Credential:
    return Credential(
        url="https://app.example.com",
        username="admin",
        email="op@example.com",
        password="secret",
    )


def test_registry_entries_are_consistent():
    for app_id, check in CHECKS.items():
        assert check.app_id == app_id
        # each app is verifiable either by an HTTP probe or an SSH DB check
        assert check.probe is not None or check.db_check is not None
        assert check.generated_login_key in {"username", "email"}


def test_resolve_login_id_by_key():
    cred = _cred()
    email_check = CHECKS["bookstack"]  # keyed by email
    user_check = CHECKS["miniflux"]  # keyed by username
    assert resolve_login_id(email_check, cred) == "op@example.com"
    assert resolve_login_id(user_check, cred) == "admin"


def test_land_grab_apps_check_registration_closed():
    for app_id in ("gitea", "forgejo", "mattermost"):
        assert CHECKS[app_id].registration_closed is not None


def test_hidden_input_extracts_csrf_token():
    html = '<input type="hidden" name="_token" value="abc123">'
    assert _hidden_input(html, "_token") == "abc123"
    assert _hidden_input(html, "missing") is None
