# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for WAF CLI commands."""

from __future__ import annotations

import json

import pytest

from hop3.commands.waf import (
    WafAppCmd,
    WafAuditCmd,
    WafCmd,
    WafLogsCmd,
    WafReloadCmd,
    WafStatsCmd,
    WafStatusCmd,
)
from hop3.config import HopConfig


@pytest.fixture
def test_hop_config(tmp_path):
    """Create a test HopConfig instance with temporary directories."""
    config = HopConfig(hop3_root=tmp_path)
    HopConfig.set_instance(config)

    # Create necessary directories
    config.WAF_ROOT.mkdir(parents=True, exist_ok=True)
    config.WAF_CONFIG.mkdir(parents=True, exist_ok=True)
    config.WAF_APPS_CONFIG.mkdir(parents=True, exist_ok=True)
    config.WAF_LOG.mkdir(parents=True, exist_ok=True)

    yield config
    HopConfig.reset_instance()


class TestWafCmd:
    """Tests for the main waf command."""

    def test_name(self):
        """Test command name."""
        assert WafCmd.name == "waf"

    def test_call_returns_help(self):
        """Test that calling waf without subcommand returns help."""
        cmd = WafCmd()
        result = cmd.call()
        assert result[0]["t"] == "text"
        assert "USAGE" in result[0]["text"]


class TestWafStatusCmd:
    """Tests for waf:status command."""

    def test_name(self):
        """Test command name."""
        assert WafStatusCmd.name == "waf:status"

    def test_status_waf_disabled(self, test_hop_config):
        """Test status when WAF is disabled."""
        cmd = WafStatusCmd()
        result = cmd.call()

        assert result[0]["t"] == "text"
        text = result[0]["text"]
        assert "WAF Enabled: No" in text
        assert "WAF is disabled" in text

    def test_status_shows_configuration(self, test_hop_config):
        """Test status shows WAF configuration details."""
        cmd = WafStatusCmd()
        result = cmd.call()

        text = result[0]["text"]
        assert "WAF Engine:" in text
        assert "Default Mode:" in text
        assert "Default Paranoia Level:" in text


class TestWafLogsCmd:
    """Tests for waf:logs command."""

    def test_name(self):
        """Test command name."""
        assert WafLogsCmd.name == "waf:logs"

    def test_no_logs(self, test_hop_config):
        """Test when no logs exist."""
        cmd = WafLogsCmd()
        result = cmd.call()

        assert "No WAF logs available" in result[0]["text"]

    def test_read_logs(self, test_hop_config):
        """Test reading logs."""
        # Create a log file
        log_file = test_hop_config.WAF_LOG / "summary.log"
        log_file.write_text(
            "2025-12-03 10:00:00 | BLOCK | test-app | 192.168.1.1 | GET /api\n"
            "2025-12-03 10:01:00 | DETECT | test-app | 192.168.1.2 | POST /data\n"
        )

        cmd = WafLogsCmd()
        result = cmd.call()

        text = result[0]["text"]
        assert "BLOCK" in text
        assert "test-app" in text

    def test_filter_by_app(self, test_hop_config):
        """Test filtering logs by app name."""
        log_file = test_hop_config.WAF_LOG / "summary.log"
        log_file.write_text(
            "2025-12-03 10:00:00 | BLOCK | app1 | 192.168.1.1 | GET /api\n"
            "2025-12-03 10:01:00 | BLOCK | app2 | 192.168.1.2 | POST /data\n"
        )

        cmd = WafLogsCmd()
        result = cmd.call("--app", "app1")

        text = result[0]["text"]
        assert "app1" in text
        # app2 should be filtered out
        lines = text.strip().split("\n")
        assert all("app2" not in line for line in lines)


class TestWafAuditCmd:
    """Tests for waf:audit command."""

    def test_name(self):
        """Test command name."""
        assert WafAuditCmd.name == "waf:audit"

    def test_no_audit_logs(self, test_hop_config):
        """Test when no audit logs exist."""
        cmd = WafAuditCmd()
        result = cmd.call()

        assert "No WAF audit logs available" in result[0]["text"]

    def test_read_audit_logs(self, test_hop_config):
        """Test reading audit logs as JSON."""
        log_file = test_hop_config.WAF_LOG / "audit.log"
        event1 = {"level": "BLOCK", "app_name": "test-app", "rule_id": 942100}
        event2 = {"level": "DETECT", "app_name": "test-app", "rule_id": 941100}
        log_file.write_text(json.dumps(event1) + "\n" + json.dumps(event2) + "\n")

        cmd = WafAuditCmd()
        result = cmd.call()

        # Parse result as JSON
        events = json.loads(result[0]["text"])
        assert len(events) == 2
        assert events[0]["rule_id"] == 942100
        assert events[1]["rule_id"] == 941100


class TestWafAppCmd:
    """Tests for waf:app command."""

    def test_name(self):
        """Test command name."""
        assert WafAppCmd.name == "waf:app"

    def test_no_app_name(self):
        """Test error when no app name provided."""
        cmd = WafAppCmd()
        result = cmd.call()

        assert result[0]["t"] == "error"
        assert "Usage:" in result[0]["text"]

    def test_app_not_found(self, test_hop_config):
        """Test when app config doesn't exist."""
        cmd = WafAppCmd()
        result = cmd.call("nonexistent-app")

        assert "No WAF configuration found" in result[0]["text"]

    def test_show_app_config(self, test_hop_config):
        """Test showing app WAF configuration."""
        import yaml

        config_file = test_hop_config.WAF_APPS_CONFIG / "my-app.yaml"
        config_data = {
            "app_name": "my-app",
            "enabled": True,
            "mode": "block",
            "paranoia_level": 2,
            "ruleset": "owasp-crs",
            "rules": {
                "allow_paths": ["/health"],
                "deny_paths": ["/admin"],
            },
        }
        config_file.write_text(yaml.safe_dump(config_data))

        cmd = WafAppCmd()
        result = cmd.call("my-app")

        text = result[0]["text"]
        assert "my-app" in text
        assert "Mode: block" in text
        assert "Paranoia Level: 2" in text
        assert "Allow Paths:" in text


class TestWafStatsCmd:
    """Tests for waf:stats command."""

    def test_name(self):
        """Test command name."""
        assert WafStatsCmd.name == "waf:stats"

    def test_no_stats(self, test_hop_config):
        """Test when no audit logs exist for stats."""
        cmd = WafStatsCmd()
        result = cmd.call()

        assert "No WAF audit logs available" in result[0]["text"]

    def test_compute_stats(self, test_hop_config):
        """Test computing statistics from audit logs."""
        log_file = test_hop_config.WAF_LOG / "audit.log"
        events = [
            {"level": "BLOCK", "app_name": "app1", "rule_id": 942100},
            {"level": "BLOCK", "app_name": "app1", "rule_id": 942100},
            {"level": "DETECT", "app_name": "app1", "rule_id": 941100},
            {"level": "BLOCK", "app_name": "app2", "rule_id": 942100},
            {"level": "ALLOW", "app_name": "app1"},
            {"level": "ERROR", "app_name": "app1", "error": "test error"},
        ]
        log_file.write_text("\n".join(json.dumps(e) for e in events))

        cmd = WafStatsCmd()
        result = cmd.call()

        text = result[0]["text"]
        assert "Total Blocked: 3" in text
        assert "Total Detected: 1" in text
        assert "Total Allowed: 1" in text
        assert "Total Errors: 1" in text
        assert "Rule 942100" in text  # Most triggered rule


class TestWafReloadCmd:
    """Tests for waf:reload command."""

    def test_name(self):
        """Test command name."""
        assert WafReloadCmd.name == "waf:reload"

    def test_reload_waf_disabled(self, test_hop_config):
        """Test reload when WAF is disabled."""
        cmd = WafReloadCmd()
        result = cmd.call()

        assert result[0]["t"] == "error"
        assert "not enabled" in result[0]["text"]
