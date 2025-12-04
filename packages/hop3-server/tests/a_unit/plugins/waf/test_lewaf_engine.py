# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the LeWAF engine implementation."""

from __future__ import annotations

import pytest
import yaml

from hop3.config import HopConfig
from hop3.core.protocols import WafConfig
from hop3.plugins.waf.lewaf.engine import (
    LeWafConfigGenerator,
    LeWafEngine,
    LeWafService,
)


@pytest.fixture
def temp_waf_dirs(tmp_path):
    """Create temporary WAF directories."""
    waf_root = tmp_path / "waf"
    config_dir = waf_root / "config"
    apps_config_dir = config_dir / "apps"
    crs_dir = config_dir / "crs"
    log_dir = tmp_path / "log" / "waf"

    # Create directories
    waf_root.mkdir(parents=True)
    config_dir.mkdir(parents=True)
    apps_config_dir.mkdir(parents=True)
    crs_dir.mkdir(parents=True)
    log_dir.mkdir(parents=True)

    return {
        "waf_root": waf_root,
        "config_dir": config_dir,
        "apps_config_dir": apps_config_dir,
        "crs_dir": crs_dir,
        "log_dir": log_dir,
        "socket_path": waf_root / "lewaf.sock",
    }


@pytest.fixture
def test_hop_config(tmp_path):
    """Create a test HopConfig instance with temporary directories."""
    config = HopConfig(hop3_root=tmp_path)
    # Set up the instance for testing
    HopConfig.set_instance(config)
    yield config
    HopConfig.reset_instance()


class TestLeWafService:
    """Tests for LeWafService."""

    def test_init(self, temp_waf_dirs):
        """Test service initialization."""
        service = LeWafService(
            waf_root=temp_waf_dirs["waf_root"],
            config_dir=temp_waf_dirs["config_dir"],
            socket_path=temp_waf_dirs["socket_path"],
            log_dir=temp_waf_dirs["log_dir"],
        )

        assert service._waf_root == temp_waf_dirs["waf_root"]
        assert service._config_dir == temp_waf_dirs["config_dir"]
        assert service._socket_path == temp_waf_dirs["socket_path"]
        assert service._log_dir == temp_waf_dirs["log_dir"]

    def test_is_running_no_pidfile(self, temp_waf_dirs):
        """Test is_running returns False when no PID file exists."""
        service = LeWafService(
            waf_root=temp_waf_dirs["waf_root"],
            config_dir=temp_waf_dirs["config_dir"],
            socket_path=temp_waf_dirs["socket_path"],
            log_dir=temp_waf_dirs["log_dir"],
        )

        assert service.is_running() is False

    def test_is_running_invalid_pid(self, temp_waf_dirs):
        """Test is_running returns False for invalid PID."""
        service = LeWafService(
            waf_root=temp_waf_dirs["waf_root"],
            config_dir=temp_waf_dirs["config_dir"],
            socket_path=temp_waf_dirs["socket_path"],
            log_dir=temp_waf_dirs["log_dir"],
        )

        # Write invalid PID
        service._pidfile.write_text("not-a-number")
        assert service.is_running() is False

    def test_is_running_dead_process(self, temp_waf_dirs):
        """Test is_running returns False for non-existent process."""
        service = LeWafService(
            waf_root=temp_waf_dirs["waf_root"],
            config_dir=temp_waf_dirs["config_dir"],
            socket_path=temp_waf_dirs["socket_path"],
            log_dir=temp_waf_dirs["log_dir"],
        )

        # Write PID that doesn't exist (very high number)
        service._pidfile.write_text("999999999")
        assert service.is_running() is False

    def test_reload_touches_trigger_file(self, temp_waf_dirs):
        """Test reload touches the trigger file."""
        service = LeWafService(
            waf_root=temp_waf_dirs["waf_root"],
            config_dir=temp_waf_dirs["config_dir"],
            socket_path=temp_waf_dirs["socket_path"],
            log_dir=temp_waf_dirs["log_dir"],
        )

        assert not service._reload_trigger.exists()
        service.reload()
        assert service._reload_trigger.exists()

    def test_start_creates_directories(self, temp_waf_dirs):
        """Test start creates necessary directories."""
        # Remove directories first
        import shutil

        shutil.rmtree(temp_waf_dirs["waf_root"])

        service = LeWafService(
            waf_root=temp_waf_dirs["waf_root"],
            config_dir=temp_waf_dirs["config_dir"],
            socket_path=temp_waf_dirs["socket_path"],
            log_dir=temp_waf_dirs["log_dir"],
        )

        service.start()

        assert temp_waf_dirs["waf_root"].exists()
        assert temp_waf_dirs["config_dir"].exists()
        assert temp_waf_dirs["log_dir"].exists()


class TestLeWafConfigGenerator:
    """Tests for LeWafConfigGenerator."""

    def test_generate_app_config_basic(self, temp_waf_dirs):
        """Test generating basic app configuration."""
        generator = LeWafConfigGenerator(
            apps_config_dir=temp_waf_dirs["apps_config_dir"],
            crs_dir=temp_waf_dirs["crs_dir"],
        )

        waf_config = WafConfig(
            app_name="test-app",
            enabled=True,
            mode="block",
            paranoia_level=1,
        )

        config_path = generator.generate_app_config(waf_config)

        assert config_path.exists()
        assert config_path.name == "test-app.yaml"

        # Verify content
        with config_path.open() as f:
            config_data = yaml.safe_load(f)

        assert config_data["app_name"] == "test-app"
        assert config_data["enabled"] is True
        assert config_data["mode"] == "block"
        assert config_data["paranoia_level"] == 1

    def test_generate_app_config_with_rules(self, temp_waf_dirs):
        """Test generating app configuration with security rules."""
        generator = LeWafConfigGenerator(
            apps_config_dir=temp_waf_dirs["apps_config_dir"],
            crs_dir=temp_waf_dirs["crs_dir"],
        )

        waf_config = WafConfig(
            app_name="secure-app",
            enabled=True,
            mode="detect",
            paranoia_level=3,
            allow_paths=["/health", "/metrics"],
            deny_paths=["/admin", "/debug"],
            allow_ips=["10.0.0.0/8"],
            deny_ips=["1.2.3.4"],
            exclusions=["/api/webhook"],
            disabled_rules=[942100, 942200],
        )

        config_path = generator.generate_app_config(waf_config)

        with config_path.open() as f:
            config_data = yaml.safe_load(f)

        assert config_data["mode"] == "detect"
        assert config_data["paranoia_level"] == 3
        assert config_data["rules"]["allow_paths"] == ["/health", "/metrics"]
        assert config_data["rules"]["deny_paths"] == ["/admin", "/debug"]
        assert config_data["rules"]["allow_ips"] == ["10.0.0.0/8"]
        assert config_data["rules"]["deny_ips"] == ["1.2.3.4"]
        assert config_data["rules"]["exclusions"] == ["/api/webhook"]
        assert config_data["rules"]["disabled_rule_ids"] == [942100, 942200]

    def test_generate_app_config_with_custom_rules(self, temp_waf_dirs):
        """Test generating app configuration with custom SecLang rules."""
        generator = LeWafConfigGenerator(
            apps_config_dir=temp_waf_dirs["apps_config_dir"],
            crs_dir=temp_waf_dirs["crs_dir"],
        )

        custom_rule = (
            'SecRule REQUEST_URI "@contains /admin" "id:10001,deny,status:403"'
        )
        waf_config = WafConfig(
            app_name="custom-app",
            enabled=True,
            custom_rules=custom_rule,
        )

        config_path = generator.generate_app_config(waf_config)

        with config_path.open() as f:
            config_data = yaml.safe_load(f)

        assert config_data["custom_rules"] == custom_rule

    def test_generate_app_config_creates_directory(self, tmp_path):
        """Test config generator creates apps directory if missing."""
        apps_config_dir = tmp_path / "nonexistent" / "apps"
        crs_dir = tmp_path / "crs"

        generator = LeWafConfigGenerator(
            apps_config_dir=apps_config_dir,
            crs_dir=crs_dir,
        )

        waf_config = WafConfig(app_name="new-app", enabled=True)
        config_path = generator.generate_app_config(waf_config)

        assert apps_config_dir.exists()
        assert config_path.exists()


class TestLeWafEngine:
    """Tests for LeWafEngine."""

    def test_init(self, test_hop_config):
        """Test engine initialization."""
        engine = LeWafEngine()

        assert engine.name == "lewaf"
        assert engine._waf_root == test_hop_config.WAF_ROOT
        assert engine._config_dir == test_hop_config.WAF_CONFIG
        assert engine._socket_path == test_hop_config.WAF_SOCKET

    def test_get_upstream_socket(self, test_hop_config):
        """Test getting the upstream socket path."""
        engine = LeWafEngine()

        socket_path = engine.get_upstream_socket()
        assert socket_path == str(test_hop_config.WAF_SOCKET)

    def test_get_app_upstream(self, test_hop_config):
        """Test getting the app upstream URL."""
        engine = LeWafEngine()

        upstream = engine.get_app_upstream("my-app")
        assert upstream == f"unix:{test_hop_config.WAF_SOCKET}"

    def test_is_running_when_stopped(self, test_hop_config):
        """Test is_running returns False when service not started."""
        engine = LeWafEngine()
        assert engine.is_running() is False

    def test_configure_app_disabled(self, test_hop_config):
        """Test configure_app skips when WAF disabled for app."""
        engine = LeWafEngine()

        # Ensure directories exist
        engine._apps_config_dir.mkdir(parents=True, exist_ok=True)

        waf_config = WafConfig(
            app_name="disabled-app",
            enabled=False,
        )

        engine.configure_app(waf_config)

        # Verify no config file was created
        config_file = engine._apps_config_dir / "disabled-app.yaml"
        assert not config_file.exists()

    def test_configure_app_enabled(self, test_hop_config):
        """Test configure_app generates config when WAF enabled."""
        engine = LeWafEngine()

        # Ensure directories exist
        engine._apps_config_dir.mkdir(parents=True, exist_ok=True)

        waf_config = WafConfig(
            app_name="enabled-app",
            enabled=True,
            mode="block",
            paranoia_level=2,
        )

        engine.configure_app(waf_config)

        # Check config file was created
        config_file = engine._apps_config_dir / "enabled-app.yaml"
        assert config_file.exists()

    def test_remove_app(self, test_hop_config):
        """Test removing app configuration."""
        engine = LeWafEngine()

        # Create config file first
        engine._apps_config_dir.mkdir(parents=True, exist_ok=True)
        config_file = engine._apps_config_dir / "to-remove.yaml"
        config_file.write_text("app_name: to-remove\n")

        assert config_file.exists()

        engine.remove_app("to-remove")

        assert not config_file.exists()

    def test_remove_app_nonexistent(self, test_hop_config):
        """Test removing non-existent app config doesn't raise error."""
        engine = LeWafEngine()

        # Should not raise
        engine.remove_app("nonexistent-app")


class TestLeWafPlugin:
    """Tests for LeWAF plugin registration."""

    def test_plugin_instance(self):
        """Test plugin instance is created."""
        from hop3.plugins.waf.lewaf.plugin import plugin

        assert plugin.name == "lewaf"

    def test_get_waf_engines(self):
        """Test get_waf_engines returns LeWafEngine."""
        from hop3.plugins.waf.lewaf.plugin import plugin

        engines = plugin.get_waf_engines()
        assert len(engines) == 1
        assert engines[0] is LeWafEngine
