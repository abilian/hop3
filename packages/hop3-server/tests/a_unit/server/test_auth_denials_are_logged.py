# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
An auth denial must say why, especially when the cause is not the token.

`is_token_revoked` fails closed for admin-scoped tokens on a database error —
deliberately, since a false-allow on admin scope is worse than a false-deny.
But it discarded the exception, so a valid token could be denied with nothing
anywhere recording that a DB error, not a revocation, is what denied it.

The caller then sees "Authentication required" and reasonably concludes their
credentials are wrong. A 34-app catalog run failed exactly this way; hours went
into the installer, supervisor state and listening ports before the per-app log
turned out to say "Authentication required" all along, with no server-side
trace of the cause.

The decision stays. The silence does not.
"""

from __future__ import annotations

import pytest

from hop3.server.security import tokens


@pytest.fixture
def broken_session(monkeypatch):
    """Make the revocation lookup raise, as a DB outage would."""

    def explode(*_args, **_kwargs):
        msg = "database is locked"
        raise RuntimeError(msg)

    monkeypatch.setattr("hop3.server.lib.database.get_session", explode, raising=False)


@pytest.fixture
def captured_errors(monkeypatch):
    records: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        tokens.server_log, "error", lambda msg, **kw: records.append((msg, kw))
    )
    return records


def test_a_denied_admin_token_records_the_cause(broken_session, captured_errors):
    denied = tokens.is_token_revoked("some-jti", scopes=["authenticated", "admin"])

    assert denied is True, "admin scope must still fail closed"
    assert captured_errors, "the reason for the denial must be recorded"
    _msg, fields = captured_errors[0]
    assert fields["is_admin"] is True
    assert "database is locked" in fields["error"]
    assert fields["jti"] == "some-jti"


def test_an_allowed_user_token_still_records_the_cause(broken_session, captured_errors):
    """Failing open is just as invisible, and just as worth knowing about."""
    revoked = tokens.is_token_revoked("some-jti", scopes=["authenticated"])

    assert revoked is False, "user scope must still fail open"
    assert captured_errors
    assert captured_errors[0][1]["is_admin"] is False
