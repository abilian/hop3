# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: AGPL-3.0-only

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
