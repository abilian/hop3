# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Both ways of running a check must hand it the same credentials.

A check is run twice in a catalog run: at the end of the deploy, by
`run_app_check`, and again by hop3-testing, which uploads the script and
executes it on the server. The second read the encrypted credential store and
exported ``HOP3_ADMIN_*`` alone, so ``Check.has_probe`` was false for every app
it tested and every check silently fell back to the operator's credential —
the weaker claim, made without saying so.

Piwigo turned that from weaker into wrong. On an empty gallery Piwigo answers
an onboarding interstitial to a guest or an administrator on *every* page, and
to an ordinary user it does not; the probe is an ordinary user. The deploy's
smoke test signed in as the probe and passed, the harness signed in as the
administrator and reported the application broken, in the same minute, from
the same file.

`check_credentials` is now the only answer to "which credentials", so the two
callers cannot disagree again.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from hop3.core.env import Env
from hop3.deployers.probe_account import PROBE_CREATED_ENV
from hop3.server.checks.runner import check_credentials

ADMIN = {
    "username": "admin",
    "email": "op@example.com",
    "password": "admin-pw",
    "login": "email",
}

PROBE = {
    "HOP3_PROBE_USER": "hop3probe",
    "HOP3_PROBE_EMAIL": "probe@hop3.invalid",
    "HOP3_PROBE_PASSWORD": "probe-pw",
}


def _app(**runtime_env: str):
    env = {"HOST_NAME": "piwigo.example.com", **runtime_env}
    return SimpleNamespace(name="piwigo", get_runtime_env=lambda: Env(env))


@pytest.fixture
def admin_credential(monkeypatch):
    monkeypatch.setattr(
        "hop3.server.checks.runner.read_admin_credential", lambda app, session: ADMIN
    )


@pytest.fixture
def no_credential(monkeypatch):
    monkeypatch.setattr(
        "hop3.server.checks.runner.read_admin_credential", lambda app, session: None
    )


class TestTheProbeTravelsWithTheAdmin:
    def test_a_created_probe_is_handed_over(self, admin_credential):
        creds = check_credentials(_app(**PROBE, **{PROBE_CREATED_ENV: "1"}), object())

        assert creds["HOP3_PROBE_PASSWORD"] == "probe-pw"
        assert creds["HOP3_PROBE_USER"] == "hop3probe"
        assert creds["HOP3_PROBE_EMAIL"] == "probe@hop3.invalid"

    def test_the_admin_still_travels_too(self, admin_credential):
        """A check may need both: sign in as the probe, assert on the admin."""
        creds = check_credentials(_app(**PROBE, **{PROBE_CREATED_ENV: "1"}), object())

        assert creds["HOP3_ADMIN_PASSWORD"] == "admin-pw"

    def test_the_admin_says_which_field_it_signs_in_with(self, admin_credential):
        """The browser harness fills the field the app's form takes."""
        creds = check_credentials(_app(), object())

        assert creds["HOP3_ADMIN_LOGIN"] == "email"

    def test_an_app_with_a_probe_and_no_admin_still_gets_its_probe(self, no_credential):
        creds = check_credentials(_app(**PROBE, **{PROBE_CREATED_ENV: "1"}), object())

        assert creds["HOP3_PROBE_PASSWORD"] == "probe-pw"
        assert "HOP3_ADMIN_PASSWORD" not in creds


class TestAnUncreatedProbeIsNotOffered:
    """
    ``HOP3_PROBE_*`` is injected so the recipe's own `create` command can make
    the account. If that command failed, the variables remain and name an
    account nobody made — signing in as it reports the application broken when
    the application is fine.
    """

    def test_without_the_marker_the_probe_is_withheld(self, admin_credential):
        creds = check_credentials(_app(**PROBE), object())

        assert not any(name.startswith("HOP3_PROBE_") for name in creds)

    def test_the_admin_is_what_is_left(self, admin_credential):
        creds = check_credentials(_app(**PROBE), object())

        assert creds["HOP3_ADMIN_PASSWORD"] == "admin-pw"


class TestNothingIsInvented:
    def test_an_app_with_neither_gets_nothing(self, no_credential):
        assert check_credentials(_app(), object()) == {}

    def test_an_app_that_declares_no_probe_gets_no_probe_keys(self, admin_credential):
        creds = check_credentials(_app(), object())

        assert set(creds) == {
            "HOP3_ADMIN_USER",
            "HOP3_ADMIN_EMAIL",
            "HOP3_ADMIN_PASSWORD",
            "HOP3_ADMIN_LOGIN",
        }
