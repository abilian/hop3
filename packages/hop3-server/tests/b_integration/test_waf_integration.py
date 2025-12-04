# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for WAF deployment flow.

These tests verify that WAF is properly configured during app deployment
and that the WAF engine correctly generates configuration files.

Note: Some tests require the lewaf package to be installed.
Tests that require lewaf will be skipped if the package is not available.
"""

from __future__ import annotations

import pytest
import yaml

from hop3.config import HopConfig
from hop3.core.protocols import WafConfig
from hop3.plugins.waf.lewaf.engine import (
    LEWAF_AVAILABLE,
    LeWafConfigGenerator,
    LeWafEngine,
)
from hop3.project.hop3_config import Hop3Config

# Skip marker for tests that require lewaf
requires_lewaf = pytest.mark.skipif(
    not LEWAF_AVAILABLE,
    reason="LeWAF package not installed",
)


@pytest.fixture
def waf_test_config(tmp_path):
    """Create a test HopConfig with WAF enabled."""
    config = HopConfig(hop3_root=tmp_path)
    HopConfig.set_instance(config)

    # Create all necessary directories
    config.WAF_ROOT.mkdir(parents=True, exist_ok=True)
    config.WAF_CONFIG.mkdir(parents=True, exist_ok=True)
    config.WAF_APPS_CONFIG.mkdir(parents=True, exist_ok=True)
    config.WAF_CRS.mkdir(parents=True, exist_ok=True)
    config.WAF_LOG.mkdir(parents=True, exist_ok=True)

    yield config
    HopConfig.reset_instance()


@pytest.fixture
def sample_app_with_waf(tmp_path):
    """Create a sample app directory with hop3.toml WAF configuration."""
    app_dir = tmp_path / "apps" / "test-app"
    src_dir = app_dir / "src"
    src_dir.mkdir(parents=True)

    # Create hop3.toml with WAF enabled
    hop3_toml = src_dir / "hop3.toml"
    hop3_toml.write_text("""
[metadata]
id = "test-app"

[run]
start = "python app.py"

[waf]
enabled = true
engine = "lewaf"
ruleset = "owasp-crs"
paranoia_level = 2
mode = "block"

[waf.exclusions]
paths = ["/api/webhook", "/health"]
rule_ids = [942100]

[security.rules]
allow = ["/metrics"]
deny = ["/admin/debug"]
allow_ips = ["10.0.0.0/8"]
deny_ips = ["1.2.3.4"]
""")

    return app_dir


@pytest.fixture
def sample_app_no_waf(tmp_path):
    """Create a sample app directory without WAF configuration."""
    app_dir = tmp_path / "apps" / "no-waf-app"
    src_dir = app_dir / "src"
    src_dir.mkdir(parents=True)

    # Create hop3.toml without WAF
    hop3_toml = src_dir / "hop3.toml"
    hop3_toml.write_text("""
[metadata]
id = "no-waf-app"

[run]
start = "python app.py"
""")

    return app_dir


class TestWafConfigParsing:
    """Test WAF configuration parsing from hop3.toml."""

    def test_parse_waf_enabled_app(self, sample_app_with_waf):
        """Test parsing hop3.toml with WAF enabled."""
        hop3_toml = sample_app_with_waf / "src" / "hop3.toml"
        config = Hop3Config.from_file(hop3_toml)

        assert config.waf_enabled is True
        assert config.waf_engine == "lewaf"
        assert config.waf_ruleset == "owasp-crs"
        assert config.waf_paranoia_level == 2
        assert config.waf_mode == "block"

        # Check exclusions
        assert config.waf_exclusions["paths"] == ["/api/webhook", "/health"]
        assert config.waf_exclusions["rule_ids"] == [942100]

        # Check security rules
        assert config.security_allow_paths == ["/metrics"]
        assert config.security_deny_paths == ["/admin/debug"]
        assert config.security_allow_ips == ["10.0.0.0/8"]
        assert config.security_deny_ips == ["1.2.3.4"]

    def test_parse_no_waf_app(self, sample_app_no_waf):
        """Test parsing hop3.toml without WAF configuration."""
        hop3_toml = sample_app_no_waf / "src" / "hop3.toml"
        config = Hop3Config.from_file(hop3_toml)

        assert config.waf_enabled is False
        assert config.waf_engine == "lewaf"  # default
        assert config.waf_paranoia_level == 1  # default

    def test_get_waf_config_dict(self, sample_app_with_waf):
        """Test building WafConfig dict from hop3.toml."""
        hop3_toml = sample_app_with_waf / "src" / "hop3.toml"
        config = Hop3Config.from_file(hop3_toml)

        waf_config = config.get_waf_config("test-app")

        assert waf_config["app_name"] == "test-app"
        assert waf_config["enabled"] is True
        assert waf_config["engine"] == "lewaf"
        assert waf_config["paranoia_level"] == 2
        assert waf_config["exclusions"] == ["/api/webhook", "/health"]
        assert waf_config["disabled_rules"] == [942100]
        assert waf_config["allow_paths"] == ["/metrics"]
        assert waf_config["deny_paths"] == ["/admin/debug"]


@requires_lewaf
class TestLeWafEngineIntegration:
    """Test LeWAF engine integration.

    These tests require the lewaf package to be installed.
    """

    def test_engine_initialization(self, waf_test_config):
        """Test LeWAF engine initializes with correct paths."""
        engine = LeWafEngine()

        assert engine._waf_root == waf_test_config.WAF_ROOT
        assert engine._config_dir == waf_test_config.WAF_CONFIG
        assert engine._apps_config_dir == waf_test_config.WAF_APPS_CONFIG
        assert engine._socket_path == waf_test_config.WAF_SOCKET

    def test_configure_app_generates_yaml(self, waf_test_config, sample_app_with_waf):
        """Test that configure_app generates proper YAML config."""
        engine = LeWafEngine()

        # Create WafConfig from hop3.toml
        hop3_toml = sample_app_with_waf / "src" / "hop3.toml"
        hop3_config = Hop3Config.from_file(hop3_toml)
        waf_config_dict = hop3_config.get_waf_config("test-app")

        waf_config = WafConfig(
            app_name=waf_config_dict["app_name"],
            enabled=waf_config_dict["enabled"],
            engine=waf_config_dict["engine"],
            ruleset=waf_config_dict["ruleset"],
            paranoia_level=waf_config_dict["paranoia_level"],
            mode=waf_config_dict["mode"],
            exclusions=waf_config_dict["exclusions"],
            disabled_rules=waf_config_dict["disabled_rules"],
            custom_rules=waf_config_dict["custom_rules"],
            allow_paths=waf_config_dict["allow_paths"],
            deny_paths=waf_config_dict["deny_paths"],
            allow_ips=waf_config_dict["allow_ips"],
            deny_ips=waf_config_dict["deny_ips"],
        )

        # Configure app
        engine.configure_app(waf_config)

        # Verify config file was created
        config_file = waf_test_config.WAF_APPS_CONFIG / "test-app.yaml"
        assert config_file.exists()

        # Verify content
        with config_file.open() as f:
            saved_config = yaml.safe_load(f)

        assert saved_config["app_name"] == "test-app"
        assert saved_config["enabled"] is True
        assert saved_config["mode"] == "block"
        assert saved_config["paranoia_level"] == 2
        assert saved_config["rules"]["allow_paths"] == ["/metrics"]
        assert saved_config["rules"]["deny_paths"] == ["/admin/debug"]
        assert saved_config["rules"]["exclusions"] == ["/api/webhook", "/health"]
        assert saved_config["rules"]["disabled_rule_ids"] == [942100]

    def test_configure_app_skips_disabled(self, waf_test_config):
        """Test that configure_app skips when WAF disabled."""
        engine = LeWafEngine()

        waf_config = WafConfig(
            app_name="disabled-app",
            enabled=False,
        )

        engine.configure_app(waf_config)

        # Verify no config file was created
        config_file = waf_test_config.WAF_APPS_CONFIG / "disabled-app.yaml"
        assert not config_file.exists()

    def test_remove_app_deletes_config(self, waf_test_config):
        """Test that remove_app deletes config file."""
        engine = LeWafEngine()

        # First create config
        waf_config = WafConfig(app_name="to-remove", enabled=True)
        engine.configure_app(waf_config)

        config_file = waf_test_config.WAF_APPS_CONFIG / "to-remove.yaml"
        assert config_file.exists()

        # Remove app
        engine.remove_app("to-remove")
        assert not config_file.exists()

    def test_multiple_apps(self, waf_test_config):
        """Test configuring multiple apps."""
        engine = LeWafEngine()

        apps = [
            WafConfig(app_name="app1", enabled=True, paranoia_level=1),
            WafConfig(app_name="app2", enabled=True, paranoia_level=2),
            WafConfig(app_name="app3", enabled=True, paranoia_level=3),
        ]

        for app_config in apps:
            engine.configure_app(app_config)

        # Verify all config files exist
        for app_config in apps:
            config_file = (
                waf_test_config.WAF_APPS_CONFIG / f"{app_config.app_name}.yaml"
            )
            assert config_file.exists()

            with config_file.open() as f:
                saved_config = yaml.safe_load(f)
            assert saved_config["paranoia_level"] == app_config.paranoia_level


class TestWafConfigGenerator:
    """Test WAF configuration file generation."""

    def test_generate_config_with_all_rules(self, tmp_path):
        """Test generating config with all rule types."""
        apps_config_dir = tmp_path / "apps"
        crs_dir = tmp_path / "crs"

        generator = LeWafConfigGenerator(
            apps_config_dir=apps_config_dir,
            crs_dir=crs_dir,
        )

        waf_config = WafConfig(
            app_name="full-config-app",
            enabled=True,
            engine="lewaf",
            ruleset="owasp-crs",
            paranoia_level=3,
            mode="detect",
            exclusions=["/api/internal", "/debug"],
            disabled_rules=[942100, 942200, 941100],
            custom_rules='SecRule REQUEST_URI "@contains /secret" "id:100001,deny"',
            allow_paths=["/public", "/static"],
            deny_paths=["/admin", "/.git"],
            allow_ips=["192.168.0.0/16", "10.0.0.1"],
            deny_ips=["0.0.0.0/8"],
        )

        config_path = generator.generate_app_config(waf_config)

        assert config_path.exists()
        assert config_path.name == "full-config-app.yaml"

        with config_path.open() as f:
            saved_config = yaml.safe_load(f)

        # Verify all fields
        assert saved_config["app_name"] == "full-config-app"
        assert saved_config["enabled"] is True
        assert saved_config["mode"] == "detect"
        assert saved_config["paranoia_level"] == 3
        assert saved_config["ruleset"] == "owasp-crs"
        assert (
            saved_config["custom_rules"]
            == 'SecRule REQUEST_URI "@contains /secret" "id:100001,deny"'
        )

        rules = saved_config["rules"]
        assert rules["allow_paths"] == ["/public", "/static"]
        assert rules["deny_paths"] == ["/admin", "/.git"]
        assert rules["allow_ips"] == ["192.168.0.0/16", "10.0.0.1"]
        assert rules["deny_ips"] == ["0.0.0.0/8"]
        assert rules["exclusions"] == ["/api/internal", "/debug"]
        assert rules["disabled_rule_ids"] == [942100, 942200, 941100]


@requires_lewaf
class TestWafServiceIntegration:
    """Test WAF service management integration.

    These tests require the lewaf package to be installed.
    """

    def test_service_directories_created(self, waf_test_config):
        """Test that service start creates directories."""
        engine = LeWafEngine()
        engine.service.start()

        assert waf_test_config.WAF_ROOT.exists()
        assert waf_test_config.WAF_CONFIG.exists()
        assert waf_test_config.WAF_LOG.exists()

    def test_service_reload_trigger(self, waf_test_config):
        """Test that reload touches trigger file."""
        engine = LeWafEngine()
        reload_trigger = waf_test_config.WAF_CONFIG / ".reload"

        assert not reload_trigger.exists()

        engine.service.reload()

        assert reload_trigger.exists()

    def test_service_not_running_initially(self, waf_test_config):
        """Test is_running returns False when no PID file."""
        engine = LeWafEngine()
        assert engine.is_running() is False

    def test_upstream_socket_path(self, waf_test_config):
        """Test upstream socket path is correct."""
        engine = LeWafEngine()
        socket_path = engine.get_upstream_socket()

        assert socket_path == str(waf_test_config.WAF_SOCKET)
        assert "lewaf.sock" in socket_path
