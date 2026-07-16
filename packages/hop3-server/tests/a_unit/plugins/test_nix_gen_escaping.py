# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Tests for Nix string escaping."""

from __future__ import annotations

from hop3.plugins.build.nix.gen.escaping import nix_escape


def test_escapes_variable_interpolation():
    assert nix_escape("${VAR}") == "''${VAR}"


def test_escapes_default_value():
    assert nix_escape("${PORT:-8080}") == "''${PORT:-8080}"


def test_passes_through_bare_dollar_var():
    assert nix_escape("$VAR") == "$VAR"


def test_passes_through_command_substitution():
    assert nix_escape("$(date)") == "$(date)"
    assert nix_escape("$(head -c 32 /dev/urandom | base64)") == (
        "$(head -c 32 /dev/urandom | base64)"
    )


def test_passes_through_pwd():
    assert nix_escape("$PWD") == "$PWD"


def test_escapes_in_mixed_content():
    text = "HOST=${PGHOST:-localhost} USER=$(whoami) PWD=$PWD"
    expected = "HOST=''${PGHOST:-localhost} USER=$(whoami) PWD=$PWD"
    assert nix_escape(text) == expected


def test_escapes_multiple_occurrences():
    text = "${A} ${B} ${C}"
    assert nix_escape(text) == "''${A} ''${B} ''${C}"


def test_empty_string():
    assert nix_escape("") == ""


# --- quotes: sequences that used to emit un-parseable Nix, silently ------------
#
# Inside a Nix ''...'' string only `''` and `${` are special. A literal `''` (PHP's
# empty string) therefore TERMINATED the string, and a lone `'` sitting next to an
# escape merged with it into `'''`, which Nix reads as the literal-'' escape — so
# `'${MYSQL_HOST}'` turned the interpolation into a REAL one and the build died
# with "undefined variable 'MYSQL_HOST'". Both shipped broken hop3.nix with no
# warning (witnessed: easy-appointments, wordpress).
#
# The expected values below were verified by round-tripping through real Nix
# (nix-instantiate --eval): `'' <escaped> ''` must evaluate back to the input.


def test_escapes_literal_empty_quotes():
    # PHP/JS empty string — `'''` is Nix's escape for a literal `''`.
    assert nix_escape("const X = '';") == "const X = ''';"


def test_escapes_quote_adjacent_to_interpolation():
    # The single-quoted-value case: the quote must not merge with the `''${`.
    assert (
        nix_escape("const H = '${MYSQL_HOST}';") == "const H = ''\\'''${MYSQL_HOST}';"
    )


def test_escapes_trailing_quote():
    # A trailing quote would otherwise swallow the enclosing string's closing ''.
    assert nix_escape("echo '${A}'") == "echo ''\\'''${A}''\\'"
    assert nix_escape("x'") == "x''\\'"


def test_lone_quote_not_adjacent_to_escape_is_left_alone():
    # No need to escape a quote that can't touch a `''` — keep output readable.
    assert nix_escape("const L = 'english';") == "const L = 'english';"


def test_bare_dollar_var_needs_no_escape_but_trailing_quote_still_does():
    # `$VAR` (no braces) is not Nix interpolation, so the quotes around it stay
    # plain — except the trailing one, which would touch the closing ''.
    assert nix_escape("'$MYSQL_HOST'") == "'$MYSQL_HOST''\\'"
