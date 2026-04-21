# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for hop3_installer.server_installer.config."""

from __future__ import annotations

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
