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
from hop3.plugins.build.nix.gen.templates.base import ReproTier


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


def test_every_template_declares_a_tier():
    """The tier is what an auditor reads; an undeclared one would read as Tier-1."""
    for name in list_templates():
        assert isinstance(get_template(name).tier, ReproTier), name


def test_tiers_match_how_each_template_gets_its_artefact():
    """Pin the classification: a template that stops building from source (or
    starts) must move tier here too, or the published label silently lies."""
    by_tier: dict[ReproTier, set[str]] = {t: set() for t in ReproTier}
    for name in list_templates():
        by_tier[get_template(name).tier].add(name)

    assert by_tier[ReproTier.SOURCE] == {
        "go-source",
        "java-gradle",
        "node-pnpm-install",
        "php-app",
        "python-venv",
        "ruby-bundler",
    }
    assert by_tier[ReproTier.NIXPKGS] == {"nixpkgs-wrapper"}
    assert by_tier[ReproTier.PREBUILT] == {
        "java-war",
        "node-prebuilt",
        "prebuilt-archive",
        "prebuilt-binary",
    }


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
