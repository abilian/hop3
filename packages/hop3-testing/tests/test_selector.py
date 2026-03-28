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

    def test_dev_mode(self):
        """Test dev mode configuration."""
        config = MODES["dev"]

        assert config.name == "dev"
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

    def test_nightly_mode(self):
        """Test nightly mode configuration."""
        config = MODES["nightly"]

        assert config.name == "nightly"
        assert "fast" in config.tiers
        assert "medium" in config.tiers
        assert "slow" in config.tiers
        assert "P0" in config.priorities
        assert "P1" in config.priorities

    def test_release_mode(self):
        """Test release mode includes everything."""
        config = MODES["release"]

        assert config.name == "release"
        assert len(config.tiers) == 4
        assert len(config.priorities) == 3

    def test_all_modes_have_required_fields(self):
        """Test all predefined modes have required fields."""
        for name, config in MODES.items():
            assert config.name == name
            assert len(config.tiers) > 0
            assert len(config.priorities) > 0
            assert len(config.targets) > 0


class TestGetModeConfig:
    """Tests for get_mode_config function."""

    def test_get_valid_mode(self):
        """Test getting a valid mode."""
        config = get_mode_config("dev")
        assert config.name == "dev"

    def test_get_all_valid_modes(self):
        """Test getting all valid modes."""
        for mode_name in ["dev", "ci", "nightly", "release"]:
            config = get_mode_config(mode_name)
            assert config.name == mode_name

    def test_get_invalid_mode_raises(self):
        """Test getting an invalid mode raises ValueError."""
        with pytest.raises(ValueError, match="Unknown mode"):
            get_mode_config("invalid")


class TestListModes:
    """Tests for list_modes function."""

    def test_list_modes_returns_all(self):
        """Test list_modes returns all available modes."""
        modes = list_modes()

        assert "dev" in modes
        assert "ci" in modes
        assert "nightly" in modes
        assert "release" in modes
        assert len(modes) == 4
