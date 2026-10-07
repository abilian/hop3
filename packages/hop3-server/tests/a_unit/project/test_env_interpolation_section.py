# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
``${VAR}`` belongs in ``[env.computed]``, and nowhere else.

A plain ``[env]`` value is literal — exported single-quoted, verbatim, into
the app's environment. Writing an interpolation there fails silently and
totally. Grafana's recipe did: it received
``GF_DATABASE_HOST=${PGHOST}:${PGPORT}`` and ``GF_SERVER_HTTP_PORT=${PORT:-8080}``
as those exact strings, so it quietly fell back to SQLite and to its own
default port 3000 — while Hop3 had provisioned a PostgreSQL addon it never
opened and pointed the proxy at a port it never bound. The deploy read green
until the readiness gate timed out sixty seconds later, and the diagnosis
looked like a slow app.

Nothing in the recipe was ambiguous; only the section was wrong. So the
platform says so, at validation, where ``hop3check`` runs it.
"""

from __future__ import annotations

import pytest

from hop3.project.schema import Hop3TomlValidationError, validate_hop3_toml

BASE = {"metadata": {"id": "grafana"}}


def _validate(extra: dict) -> None:
    validate_hop3_toml(BASE | extra)


def _error(extra: dict) -> str:
    with pytest.raises(Hop3TomlValidationError) as exc:
        _validate(extra)
    return str(exc.value)


class TestALiteralSectionRefusesAnInterpolation:
    def test_a_bare_reference_is_refused(self):
        message = _error({"env": {"GF_DATABASE_NAME": "${PGDATABASE}"}})
        assert "GF_DATABASE_NAME" in message
        assert "[env.computed]" in message

    def test_a_default_expression_is_refused(self):
        """``${PORT:-8080}`` is shell syntax, and no shell reads this value."""
        message = _error({"env": {"GF_SERVER_HTTP_PORT": "${PORT:-8080}"}})
        assert "GF_SERVER_HTTP_PORT" in message

    def test_a_reference_embedded_in_a_larger_value_is_refused(self):
        """The shape that sent Grafana to SQLite."""
        message = _error({"env": {"GF_DATABASE_HOST": "${PGHOST}:${PGPORT}"}})
        assert "[env.computed]" in message

    def test_a_context_env_is_held_to_the_same_rule(self):
        message = _error({"contexts": {"prod": {"env": {"DB_HOST": "${PGHOST}"}}}})
        assert "[contexts.*.env]" in message


class TestAValueThatIsOnlyABareReference:
    """
    ``NITRO_PORT = "$PORT"``, from the Nuxt tutorial: no braces, so the
    ``${VAR}`` check let it through, and Node died on
    ``options.port should be >= 0 and < 65536. Received type string ('$PORT')``.
    """

    def test_the_port_is_refused_with_the_start_line_remedy(self):
        message = _error({"env": {"NITRO_PORT": "$PORT"}})
        assert "NITRO_PORT" in message
        assert "[run].start" in message

    def test_an_addon_variable_points_at_the_computed_section(self):
        message = _error({"env": {"DB_HOST": "$PGHOST"}})
        assert "[env.computed]" in message
        assert "${PGHOST}" in message


class TestTheRemedyIsTheOneThatWorks:
    """
    Three references, three different right answers. Naming the wrong one
    sends the reader to a section where the value is just as inert.
    """

    def test_an_addon_reference_belongs_in_the_computed_section(self):
        assert "[env.computed]" in _error({"env": {"DB": "${PGDATABASE}"}})

    def test_the_port_is_not_available_to_any_env_section(self):
        """
        It is allocated after they are resolved, so "move it to
        [env.computed]" would be advice the reader cannot act on.
        """
        message = _error({"env": {"GF_SERVER_HTTP_PORT": "${PORT}"}})
        assert "[run].start" in message
        assert "Move it to [env.computed]" not in message

    def test_a_default_is_not_offered_a_section_that_cannot_parse_it(self):
        """`[env.computed]` interpolates ${VAR}, and only that."""
        message = _error({"env": {"DB_PORT": "${PGPORT:-5432}"}})
        assert "no ${VAR:-default} form" in message


class TestWhatStaysLegal:
    def test_the_computed_section_is_where_interpolation_lives(self):
        _validate({"env": {"computed": {"GF_DATABASE_NAME": "${PGDATABASE}"}}})

    def test_a_plain_value_is_untouched(self):
        _validate({"env": {"GF_SECURITY_ADMIN_USER": "admin"}})

    def test_a_lone_dollar_sign_is_not_an_interpolation(self):
        """A price, a regex, a shell variable the app expands itself."""
        _validate({"env": {"CURRENCY": "$", "PROMPT": "$PORT is not ${"}})

    def test_a_dollar_inside_a_longer_value_is_left_alone(self):
        """Only a value that is nothing but `$NAME` is the mistake."""
        _validate({"env": {"GREETING": "costs $5", "TEMPLATE": "$HOME/data"}})

    def test_a_generated_secret_is_still_a_table_not_a_string(self):
        _validate({"env": {"SECRET_KEY": {"generate": "hex", "length": 32}}})
