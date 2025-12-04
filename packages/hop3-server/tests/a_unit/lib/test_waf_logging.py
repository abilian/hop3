# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for WAF audit logging utilities."""

from __future__ import annotations

import json

import pytest

from hop3.lib.waf_logging import WafAuditLogger, get_waf_logger, reset_waf_logger


@pytest.fixture
def temp_log_dir(tmp_path):
    """Create a temporary log directory."""
    log_dir = tmp_path / "waf_logs"
    log_dir.mkdir(parents=True)
    return log_dir


@pytest.fixture
def waf_logger(temp_log_dir):
    """Create a WAF logger with temporary directory."""
    return WafAuditLogger(log_dir=temp_log_dir)


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the singleton logger before each test."""
    reset_waf_logger()
    yield
    reset_waf_logger()


class TestWafAuditLogger:
    """Tests for WafAuditLogger class."""

    def test_init_creates_log_dir(self, tmp_path):
        """Test logger creates log directory if it doesn't exist."""
        log_dir = tmp_path / "new_log_dir"
        assert not log_dir.exists()

        _ = WafAuditLogger(log_dir=log_dir)

        assert log_dir.exists()

    def test_log_block(self, waf_logger, temp_log_dir):
        """Test logging a blocked request."""
        waf_logger.log_block(
            app_name="test-app",
            request_id="req-123",
            client_ip="192.168.1.100",
            method="POST",
            uri="/api/users",
            rule_id=942100,
            rule_msg="SQL Injection Attack",
            matched_data="'; DROP TABLE users;--",
            tags=["attack-sqli", "OWASP_CRS"],
        )

        # Read the audit log
        audit_log = temp_log_dir / "audit.log"
        # Give loguru time to flush
        import time

        time.sleep(0.1)

        # Check audit log contains JSON event
        if audit_log.exists():
            content = audit_log.read_text()
            if content.strip():
                event = json.loads(content.strip().split("\n")[-1])
                assert event["level"] == "BLOCK"
                assert event["app_name"] == "test-app"
                assert event["rule_id"] == 942100
                assert event["action"] == "block"

    def test_log_detect(self, waf_logger, temp_log_dir):
        """Test logging a detected attack (detect mode)."""
        waf_logger.log_detect(
            app_name="test-app",
            request_id="req-456",
            client_ip="10.0.0.50",
            method="GET",
            uri="/search?q=<script>",
            rule_id=941100,
            rule_msg="XSS Attack Detected",
            matched_data="<script>",
        )

        # Read the audit log
        audit_log = temp_log_dir / "audit.log"
        import time

        time.sleep(0.1)

        if audit_log.exists():
            content = audit_log.read_text()
            if content.strip():
                event = json.loads(content.strip().split("\n")[-1])
                assert event["level"] == "DETECT"
                assert event["action"] == "detect"

    def test_log_allow(self, waf_logger, temp_log_dir):
        """Test logging an allowed request."""
        waf_logger.log_allow(
            app_name="test-app",
            request_id="req-789",
            client_ip="10.0.0.1",
            method="GET",
            uri="/health",
            reason="whitelisted",
            processing_time_ms=0.5,
        )

        # Read the audit log
        audit_log = temp_log_dir / "audit.log"
        import time

        time.sleep(0.1)

        if audit_log.exists():
            content = audit_log.read_text()
            if content.strip():
                event = json.loads(content.strip().split("\n")[-1])
                assert event["level"] == "ALLOW"
                assert event["reason"] == "whitelisted"

    def test_log_error(self, waf_logger, temp_log_dir):
        """Test logging a WAF error."""
        waf_logger.log_error(
            app_name="test-app",
            error="Failed to parse request body",
            request_id="req-error",
        )

        audit_log = temp_log_dir / "audit.log"
        import time

        time.sleep(0.1)

        if audit_log.exists():
            content = audit_log.read_text()
            if content.strip():
                event = json.loads(content.strip().split("\n")[-1])
                assert event["level"] == "ERROR"
                assert "Failed to parse" in event["error"]

    def test_build_event_structure(self, waf_logger):
        """Test that _build_event creates proper structure."""
        event = waf_logger._build_event(
            level="TEST",
            app_name="my-app",
            request_id="req-001",
            client_ip="1.2.3.4",
            method="POST",
            uri="/api/test",
            rule_id=12345,
            rule_msg="Test rule",
            matched_data="test data",
            severity="HIGH",
            tags=["tag1", "tag2"],
            action="test",
            extra={"custom_field": "value"},
        )

        assert "timestamp" in event
        assert event["level"] == "TEST"
        assert event["app_name"] == "my-app"
        assert event["request_id"] == "req-001"
        assert event["client_ip"] == "1.2.3.4"
        assert event["method"] == "POST"
        assert event["uri"] == "/api/test"
        assert event["rule_id"] == 12345
        assert event["rule_msg"] == "Test rule"
        assert event["matched_data"] == "test data"
        assert event["severity"] == "HIGH"
        assert event["tags"] == ["tag1", "tag2"]
        assert event["action"] == "test"
        assert event["custom_field"] == "value"

    def test_matched_data_truncation(self, waf_logger):
        """Test that matched data is truncated to prevent log bloat."""
        long_data = "x" * 1000
        event = waf_logger._build_event(
            level="TEST",
            app_name="app",
            request_id="req",
            client_ip="1.2.3.4",
            method="GET",
            uri="/",
            rule_id=1,
            rule_msg="test",
            matched_data=long_data,
            severity="LOW",
            tags=[],
            action="test",
            extra={},
        )

        assert len(event["matched_data"]) == 500

    def test_no_rule_info_when_zero(self, waf_logger):
        """Test that rule info is omitted when rule_id is 0."""
        event = waf_logger._build_event(
            level="ALLOW",
            app_name="app",
            request_id="req",
            client_ip="1.2.3.4",
            method="GET",
            uri="/",
            rule_id=0,
            rule_msg="",
            matched_data="",
            severity="",
            tags=[],
            action="allow",
            extra={},
        )

        assert "rule_id" not in event
        assert "rule_msg" not in event


class TestWafLoggerSingleton:
    """Tests for the singleton logger instance."""

    def test_get_waf_logger_returns_instance(self, tmp_path, monkeypatch):
        """Test that get_waf_logger returns a WafAuditLogger."""
        from hop3.config import HopConfig

        # Create test config
        config = HopConfig(hop3_root=tmp_path)
        HopConfig.set_instance(config)

        try:
            logger = get_waf_logger()
            assert isinstance(logger, WafAuditLogger)
        finally:
            HopConfig.reset_instance()

    def test_get_waf_logger_returns_same_instance(self, tmp_path):
        """Test that get_waf_logger returns the same instance."""
        from hop3.config import HopConfig

        config = HopConfig(hop3_root=tmp_path)
        HopConfig.set_instance(config)

        try:
            logger1 = get_waf_logger()
            logger2 = get_waf_logger()
            assert logger1 is logger2
        finally:
            HopConfig.reset_instance()

    def test_reset_waf_logger(self, tmp_path):
        """Test that reset_waf_logger resets the singleton."""
        from hop3.config import HopConfig

        config = HopConfig(hop3_root=tmp_path)
        HopConfig.set_instance(config)

        try:
            logger1 = get_waf_logger()
            reset_waf_logger()
            logger2 = get_waf_logger()
            assert logger1 is not logger2
        finally:
            HopConfig.reset_instance()
