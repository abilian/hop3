# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for test selector and mode configuration."""

from __future__ import annotations

import pytest
from hop3_testing.selector.modes import (
    MODES,
    ModeConfig,
    get_mode_config,
    list_modes,
)


class TestModeConfig:
    """Tests for ModeConfig dataclass."""

    def test_mode_config_creation(self):
        """Test creating a ModeConfig."""
        config = ModeConfig(
            name="test",
            tiers=["fast"],
            priorities=["P0"],
            targets=["docker"],
            description="Test mode",
        )

        assert config.name == "test"
        assert config.tiers == ["fast"]
        assert config.priorities == ["P0"]
        assert config.targets == ["docker"]
        assert config.description == "Test mode"
        assert config.max_duration_minutes is None

    def test_mode_config_with_duration(self):
        """Test ModeConfig with max_duration_minutes."""
        config = ModeConfig(
            name="test",
            tiers=["fast", "medium"],
            priorities=["P0", "P1"],
            targets=["docker"],
            max_duration_minutes=30,
        )

        assert config.max_duration_minutes == 30


class TestPredefinedModes:
    """Tests for predefined mode configurations."""

    def test_smoke_mode(self):
        """Test smoke mode configuration (was 'dev')."""
        config = MODES["smoke"]

        assert config.name == "smoke"
        assert config.tiers == ["fast"]
        assert config.priorities == ["P0"]
        assert config.targets == ["docker"]
        assert config.max_duration_minutes == 5

    def test_ci_mode(self):
        """Test CI mode configuration."""
        config = MODES["ci"]

        assert config.name == "ci"
        assert "fast" in config.tiers
        assert "medium" in config.tiers
        assert config.priorities == ["P0"]
        assert config.max_duration_minutes == 15

    def test_broad_mode(self):
        """Test broad mode configuration (the suite the nightly cron runs)."""
        config = MODES["broad"]

        assert config.name == "broad"
        assert "fast" in config.tiers
        assert "medium" in config.tiers
        assert "slow" in config.tiers
        assert "P0" in config.priorities
        assert "P1" in config.priorities

    def test_full_mode(self):
        """Test full mode includes everything (was 'release')."""
        config = MODES["full"]

        assert config.name == "full"
        assert len(config.tiers) == 4
        assert len(config.priorities) == 3

    def test_curated_mode_is_an_explicit_list(self):
        """Curated is a hand-picked explicit-list profile (filters empty)."""
        config = MODES["curated"]

        assert config.name == "curated"
        assert config.tests  # non-empty explicit list
        assert config.tiers == []  # filters ignored for explicit-list profiles

    def test_all_modes_have_required_fields(self):
        """Each predefined mode is either filter-based or an explicit list."""
        for name, config in MODES.items():
            assert config.name == name
            assert len(config.targets) > 0
            if config.tests:
                continue  # explicit-list profile bypasses tier/priority filters
            assert len(config.tiers) > 0
            assert len(config.priorities) > 0


class TestGetModeConfig:
    """Tests for get_mode_config function."""

    def test_get_valid_mode(self):
        """Test getting a valid mode."""
        config = get_mode_config("smoke")
        assert config.name == "smoke"

    def test_get_all_valid_modes(self):
        """Test getting all valid modes."""
        for mode_name in [
            "smoke",
            "ci",
            "curated",
            "tag-coverage",
            "combo-coverage",
            "broad",
            "full",
        ]:
            config = get_mode_config(mode_name)
            assert config.name == mode_name

    def test_back_compat_aliases_resolve(self):
        """Old names still resolve (dev→smoke, release→full, nightly→broad)."""
        assert get_mode_config("dev").name == "smoke"
        assert get_mode_config("release").name == "full"
        assert get_mode_config("nightly").name == "broad"

    def test_cli_mode_choices_cover_every_profile_and_alias(self):
        """The `hop3-test run --mode` choices must stay in sync with the
        profiles (+ aliases) — a hardcoded list silently rejected the renamed
        smoke/curated/full and killed every triggered run."""
        from hop3_testing.cli.commands.test import _mode_choices  # noqa: PLC0415

        choices = set(_mode_choices())
        assert set(MODES).issubset(choices)  # every built-in profile
        assert {"dev", "release", "nightly"}.issubset(choices)  # back-compat aliases

    def test_get_invalid_mode_raises(self):
        """Test getting an invalid mode raises ValueError."""
        with pytest.raises(ValueError, match="Unknown mode"):
            get_mode_config("invalid")


class TestListModes:
    """Tests for list_modes function."""

    def test_list_modes_returns_all(self):
        """Test list_modes returns all available modes."""
        modes = list_modes()

        assert "smoke" in modes
        assert "ci" in modes
        assert "curated" in modes
        assert "tag-coverage" in modes
        assert "combo-coverage" in modes
        assert "broad" in modes
        assert "full" in modes
        assert len(modes) == 7
