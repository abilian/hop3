# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Tests for the template registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from hop3.plugins.build.nix.gen.registry import get_template, list_templates
from hop3.plugins.build.nix.gen.templates import base as templates_base
from hop3.plugins.build.nix.gen.templates.base import ReproTier
from hop3.plugins.build.nix.gen.toml_adapter import app_spec_from_config


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
    """
    Pin the classification: a template that stops building from source (or
    starts) must move tier here too, or the published label silently lies.
    """
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


def test_an_unknown_template_is_rejected_at_parse_time():
    """
    The payload type *is* the template, so a spec cannot name one that does
    not exist. An unknown name can only arrive from hop3.toml, where the adapter
    catches it.
    """
    with pytest.raises(ValueError, match="Unknown template"):
        app_spec_from_config({"template": "nonexistent"}, {}, "test")


def test_no_template_hardcodes_the_default_nixpkgs_pin():
    """
    The nixpkgs header is a property of the spec, not a module constant.

    Nine templates used to interpolate ``PINNED_NIXPKGS_HEADER`` directly, so a
    per-app pin reached only two of them and a corpus-wide bump — the thing a
    pin exists to make possible — could not be expressed at all. Structural
    rather than behavioural, because each template needs a different valid spec
    to generate; what must not come back is the constant.
    """
    templates_dir = Path(templates_base.__file__).parent
    offenders = [
        path.name
        for path in sorted(templates_dir.glob("*.py"))
        if path.name != "base.py" and "PINNED_NIXPKGS_HEADER" in path.read_text()
    ]
    assert not offenders, f"these bake in the default pin: {offenders}"
