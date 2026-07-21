# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Tests for the template registry."""

from __future__ import annotations

import pytest

from hop3.plugins.build.nix.gen.registry import (
    generate,
    get_template,
    list_templates,
)
from hop3.plugins.build.nix.gen.spec import AppSpec, Source


def test_list_templates_returns_all():
    names = list_templates()
    assert len(names) == 11
    assert "java-gradle" in names
    assert "prebuilt-binary" in names
    assert "prebuilt-archive" in names
    assert "php-app" in names
    assert "node-prebuilt" in names
    assert "node-pnpm-install" in names
    assert "go-source" in names
    assert "java-war" in names
    assert "python-venv" in names
    assert "nixpkgs-wrapper" in names
    assert "ruby-bundler" in names


def test_get_template_valid():
    t = get_template("prebuilt-binary")
    assert t.name == "prebuilt-binary"


def test_get_template_invalid():
    with pytest.raises(ValueError, match="Unknown template"):
        get_template("nonexistent")


def test_get_template_error_shows_available():
    with pytest.raises(ValueError, match="prebuilt-binary"):
        get_template("typo")


def test_generate_with_invalid_template():
    spec = AppSpec(
        pname="test",
        version="1.0",
        description="test",
        template="nonexistent",
        source=Source(url="x", sha256="x"),
    )
    with pytest.raises(ValueError, match="Unknown template"):
        generate(spec)
