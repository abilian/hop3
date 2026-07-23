# Copyright (c) 2023-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Security-boundary tests for RPC command entry points.

These tests lock in the Wave-1 security-audit fixes: rejecting malicious
app names (path-traversal) and env-var keys (shell metachar injection)
before they can reach the filesystem or an `sh -c` payload.
"""

from __future__ import annotations

import pytest

from hop3.commands._helpers import get_app, parse_key_value_settings
from hop3.core.identifiers import InvalidIdentifierError


class TestGetAppRejectsPathTraversal:
    """get_app() is the main RPC choke point for app lookups."""

    @pytest.mark.parametrize(
        "bad_name",
        [
            "../etc/passwd",
            "../../etc/cron.d/evil",
            "..",
            "/absolute/path",
            "name/with/slashes",
            "name\\with\\backslashes",
            ".hidden",
            "name with space",
            "name;rm -rf /",
            "name\nnewline",
        ],
    )
    def test_rejects_malicious_names(self, db_session, bad_name: str) -> None:
        with pytest.raises(InvalidIdentifierError):
            get_app(db_session, bad_name)

    def test_valid_name_not_found_raises_value_error(self, db_session) -> None:
        # Well-formed name but no such app: different error path.
        with pytest.raises(ValueError) as exc_info:
            get_app(db_session, "nonexistent-app")
        assert not isinstance(exc_info.value, InvalidIdentifierError)

    def test_valid_name_found_returns_app(self, db_session, test_app) -> None:
        app = get_app(db_session, "testapp")
        assert app.name == "testapp"


class TestParseKeyValueSettingsRejectsShellMetacharacters:
    """
    parse_key_value_settings() feeds WebWorker.update_settings(), whose
    `sh -c "export {key}='{value}'"` interpolation is the Wave-1 critical.
    """

    @pytest.mark.parametrize(
        "payload",
        [
            "FOO;touch /tmp/pwned=bar",
            "FOO`id`=bar",
            "FOO$(whoami)=bar",
            "FOO\nBAR=bar",
            "FOO|cat=bar",
            "FOO&bar=baz",
            "FOO'quote=bar",
            'FOO"quote=bar',
        ],
    )
    def test_rejects_shell_metacharacter_keys(self, payload: str) -> None:
        parsed, errors = parse_key_value_settings([payload])
        assert parsed == {}
        assert len(errors) == 1
