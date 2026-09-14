# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
An unresolvable ``[env.computed]`` template fails the deploy.

``expand_vars`` leaves an unknown reference in place, so the old
warn-and-continue handed the app its own template as a value —
``GTS_HOST=${HOST_NAME}``, nine characters of shell syntax where a hostname
belonged — and let the deploy report success. Its sibling in the same module,
the ``[env]`` reference resolver, has always raised; this brings the two into
line and says what is missing next to what is available, so the usual cause (a
typo, or an addon that was never declared) is visible from the message.
"""

from __future__ import annotations

import pytest

from hop3.deployers.env_provisioning import _require_resolvable

ENV = {"PGHOST": "127.0.0.1", "PGPORT": "5432", "HOST_NAME": "app.example.com"}


def _error(key: str, template: str) -> str:
    with pytest.raises(ValueError) as exc:
        _require_resolvable(key, template, ENV)
    return str(exc.value)


class TestWhatResolves:
    def test_a_known_reference_passes(self):
        _require_resolvable("DB", "${PGHOST}", ENV)

    def test_several_known_references_in_one_value_pass(self):
        _require_resolvable("DB", "${PGHOST}:${PGPORT}", ENV)

    def test_a_template_with_no_reference_passes(self):
        _require_resolvable("MODE", "production", ENV)


class TestWhatDoesNot:
    def test_an_unknown_reference_is_named(self):
        message = _error("DB", "${PGDATABASE}")
        assert "${PGDATABASE}" in message
        assert "DB" in message

    def test_only_the_missing_half_is_blamed(self):
        """`${PGHOST}` resolves; saying otherwise sends the reader hunting."""
        message = _error("DB", "${PGHOST}:${NOPE}")
        assert "${NOPE}" in message
        assert "${PGHOST}," not in message

    def test_what_is_available_is_listed(self):
        """The usual cause is a typo or an undeclared addon."""
        message = _error("DB", "${PGDATABSE}")
        assert "PGHOST" in message
        assert "[[addons]]" in message

    def test_the_port_gets_its_own_answer(self):
        """
        $PORT is allocated after this section resolves, so listing the
        available variables would invite the reader to look for it there.
        """
        message = _error("GF_SERVER_HTTP_PORT", "${PORT}")
        assert "[run].start" in message
        assert "Available:" not in message

    def test_a_default_expression_is_named_as_the_unsupported_form(self):
        """`${PGPORT:-5432}` looks resolvable and is not — the form is wrong."""
        message = _error("DB_PORT", "${PGPORT:-5432}")
        assert "no ${VAR:-default} form" in message
