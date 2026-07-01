# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for hop3_installer.server_installer.config."""

from __future__ import annotations

import pytest
from hop3_installer.constants import ALL_FEATURES
from hop3_installer.server_installer.config import (
    ServerInstallerConfig,
    parse_features,
)


class TestWithFeatureFlags:
    def test_with_rust_false_by_default(self):
        cfg = ServerInstallerConfig()
        assert cfg.with_rust is False

    def test_with_rust_true_when_in_features(self):
        cfg = ServerInstallerConfig(features={"rust"})
        assert cfg.with_rust is True

    def test_existing_flags_unchanged(self):
        cfg = ServerInstallerConfig(features={"mysql", "redis", "nix"})
        assert cfg.with_mysql is True
        assert cfg.with_redis is True
        assert cfg.with_nix is True
        assert cfg.with_rust is False


class TestParseFeatures:
    def test_rust_is_recognised(self):
        assert parse_features("rust") == {"rust"}

    def test_rust_in_comma_list(self):
        assert parse_features("mysql,rust") == {"mysql", "rust"}

    def test_all_keyword_includes_rust(self):
        assert "rust" in parse_features("all")

    def test_all_features_set_includes_rust(self):
        assert "rust" in ALL_FEATURES

    def test_empty_is_empty_set(self):
        assert parse_features("") == set()

    def test_postgres_is_baseline_noop(self):
        # postgres is the always-on baseline: accepted, not returned as a feature.
        assert parse_features("postgres") == set()
        assert parse_features("mysql,postgres") == {"mysql"}

    def test_postgresql_long_spelling_also_baseline(self):
        # The cloud path passes "postgresql" (long spelling); accept it too, or a
        # `hop3-test cloud` deploy fails on "Unknown --with feature: postgresql".
        assert parse_features("postgresql") == set()
        assert parse_features("docker,mysql,postgresql") == {"docker", "mysql"}

    def test_unknown_feature_raises_loud(self):
        # The core D4 fix: an unknown --with value must not be silently dropped.
        with pytest.raises(ValueError, match="Unknown --with feature"):
            parse_features("bogus")

    def test_unknown_names_the_offender_and_lists_valid(self):
        with pytest.raises(ValueError) as exc:
            parse_features("mysql,typo")
        msg = str(exc.value)
        assert "typo" in msg
        assert "rust" in msg  # lists the valid set
        assert (
            "mysql" not in msg.split("Valid", maxsplit=1)[0]
        )  # the known one isn't the offender
