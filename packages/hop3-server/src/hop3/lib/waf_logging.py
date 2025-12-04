# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""WAF audit logging utilities.

This module provides structured JSON logging for WAF events, including:
- Request blocking events
- Rule match details
- Attack classification
- Performance metrics

Logs are written to $HOP3_ROOT/log/waf/ with automatic rotation.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    pass


class WafAuditLogger:
    """WAF audit logger with structured JSON output.

    Provides logging for WAF events with automatic file rotation
    using loguru's built-in rotation features.

    Example log format:
    {
        "timestamp": "2025-12-03T12:00:00.000000Z",
        "level": "BLOCK",
        "app_name": "my-app",
        "request_id": "abc123",
        "client_ip": "192.168.1.100",
        "method": "POST",
        "uri": "/api/users",
        "rule_id": 942100,
        "rule_msg": "SQL Injection Attack",
        "matched_data": "'; DROP TABLE users;--",
        "action": "block"
    }
    """

    def __init__(self, log_dir: Path | None = None) -> None:
        """Initialize the WAF audit logger.

        Args:
            log_dir: Directory for log files. Defaults to HOP3_ROOT/log/waf.
        """
        if log_dir is None:
            from hop3.config import HopConfig  # noqa: PLC0415

            config = HopConfig.get_instance()
            log_dir = config.WAF_LOG

        self._log_dir = log_dir
        self._log_dir.mkdir(parents=True, exist_ok=True)

        # Configure loguru for WAF audit logging
        self._configure_logger()

    def _configure_logger(self) -> None:
        """Configure loguru for WAF audit logging."""
        # Remove default handler to avoid duplicate logs
        # (we'll add our own handlers)

        # Audit log file - JSON format with rotation
        audit_log_path = self._log_dir / "audit.log"

        # Add handler for audit log with rotation
        # Rotation: 10MB per file, keep 30 files (300MB total max)
        logger.add(
            audit_log_path,
            format="{message}",  # Raw JSON output
            rotation="10 MB",
            retention=30,
            compression="gz",
            filter=lambda record: record["extra"].get("waf_audit"),
            level="DEBUG",
            serialize=False,  # We handle JSON serialization ourselves
        )

        # Summary log file - human-readable format
        summary_log_path = self._log_dir / "summary.log"

        logger.add(
            summary_log_path,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
            rotation="10 MB",
            retention=30,
            compression="gz",
            filter=lambda record: record["extra"].get("waf_summary"),
            level="INFO",
        )

    def log_block(
        self,
        *,
        app_name: str,
        request_id: str,
        client_ip: str,
        method: str,
        uri: str,
        rule_id: int,
        rule_msg: str,
        matched_data: str = "",
        severity: str = "CRITICAL",
        tags: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Log a blocked request.

        Args:
            app_name: Name of the application.
            request_id: Unique request identifier.
            client_ip: Client IP address.
            method: HTTP method (GET, POST, etc.).
            uri: Request URI.
            rule_id: CRS rule ID that triggered the block.
            rule_msg: Human-readable rule message.
            matched_data: The data that matched the rule (sanitized).
            severity: Severity level (CRITICAL, WARNING, etc.).
            tags: OWASP/CRS tags for categorization.
            extra: Additional metadata.
        """
        event = self._build_event(
            level="BLOCK",
            app_name=app_name,
            request_id=request_id,
            client_ip=client_ip,
            method=method,
            uri=uri,
            rule_id=rule_id,
            rule_msg=rule_msg,
            matched_data=matched_data,
            severity=severity,
            tags=tags or [],
            action="block",
            extra=extra or {},
        )

        # Write JSON to audit log
        logger.bind(waf_audit=True).info(json.dumps(event))

        # Write summary to summary log
        summary = f"BLOCKED {app_name} | {client_ip} | {method} {uri} | Rule {rule_id}: {rule_msg}"
        logger.bind(waf_summary=True).warning(summary)

    def log_detect(
        self,
        *,
        app_name: str,
        request_id: str,
        client_ip: str,
        method: str,
        uri: str,
        rule_id: int,
        rule_msg: str,
        matched_data: str = "",
        severity: str = "WARNING",
        tags: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Log a detected (but not blocked) attack.

        Used when WAF is in 'detect' mode (logging only).

        Args:
            app_name: Name of the application.
            request_id: Unique request identifier.
            client_ip: Client IP address.
            method: HTTP method (GET, POST, etc.).
            uri: Request URI.
            rule_id: CRS rule ID that triggered detection.
            rule_msg: Human-readable rule message.
            matched_data: The data that matched the rule (sanitized).
            severity: Severity level.
            tags: OWASP/CRS tags for categorization.
            extra: Additional metadata.
        """
        event = self._build_event(
            level="DETECT",
            app_name=app_name,
            request_id=request_id,
            client_ip=client_ip,
            method=method,
            uri=uri,
            rule_id=rule_id,
            rule_msg=rule_msg,
            matched_data=matched_data,
            severity=severity,
            tags=tags or [],
            action="detect",
            extra=extra or {},
        )

        # Write JSON to audit log
        logger.bind(waf_audit=True).info(json.dumps(event))

        # Write summary to summary log
        summary = f"DETECTED {app_name} | {client_ip} | {method} {uri} | Rule {rule_id}: {rule_msg}"
        logger.bind(waf_summary=True).info(summary)

    def log_allow(
        self,
        *,
        app_name: str,
        request_id: str,
        client_ip: str,
        method: str,
        uri: str,
        reason: str = "passed",
        processing_time_ms: float = 0.0,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Log an allowed request (for verbose/debug logging).

        Args:
            app_name: Name of the application.
            request_id: Unique request identifier.
            client_ip: Client IP address.
            method: HTTP method.
            uri: Request URI.
            reason: Reason for allowing (passed, whitelisted, etc.).
            processing_time_ms: WAF processing time in milliseconds.
            extra: Additional metadata.
        """
        event = self._build_event(
            level="ALLOW",
            app_name=app_name,
            request_id=request_id,
            client_ip=client_ip,
            method=method,
            uri=uri,
            rule_id=0,
            rule_msg="",
            matched_data="",
            severity="INFO",
            tags=[],
            action="allow",
            extra={
                "reason": reason,
                "processing_time_ms": processing_time_ms,
                **(extra or {}),
            },
        )

        # Only write to audit log (not summary) for allowed requests
        logger.bind(waf_audit=True).debug(json.dumps(event))

    def log_error(
        self,
        *,
        app_name: str,
        error: str,
        request_id: str = "",
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Log a WAF processing error.

        Args:
            app_name: Name of the application.
            error: Error message.
            request_id: Unique request identifier (if available).
            extra: Additional metadata.
        """
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": "ERROR",
            "app_name": app_name,
            "request_id": request_id,
            "error": error,
            **(extra or {}),
        }

        # Write to both logs
        logger.bind(waf_audit=True).error(json.dumps(event))
        logger.bind(waf_summary=True).error(f"ERROR {app_name} | {error}")

    def _build_event(
        self,
        *,
        level: str,
        app_name: str,
        request_id: str,
        client_ip: str,
        method: str,
        uri: str,
        rule_id: int,
        rule_msg: str,
        matched_data: str,
        severity: str,
        tags: list[str],
        action: str,
        extra: dict[str, Any],
    ) -> dict[str, Any]:
        """Build a structured audit event.

        Returns:
            Dictionary with all event fields.
        """
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": level,
            "app_name": app_name,
            "request_id": request_id,
            "client_ip": client_ip,
            "method": method,
            "uri": uri,
            "action": action,
        }

        # Add rule info if present
        if rule_id:
            event["rule_id"] = rule_id
            event["rule_msg"] = rule_msg

        if matched_data:
            # Truncate matched data to prevent log bloat
            event["matched_data"] = matched_data[:500]

        if severity:
            event["severity"] = severity

        if tags:
            event["tags"] = tags

        # Add any extra fields
        if extra:
            event.update(extra)

        return event


# Singleton instance for convenience
_waf_logger: WafAuditLogger | None = None


def get_waf_logger() -> WafAuditLogger:
    """Get the singleton WAF audit logger.

    Returns:
        WafAuditLogger instance.
    """
    global _waf_logger
    if _waf_logger is None:
        _waf_logger = WafAuditLogger()
    return _waf_logger


def reset_waf_logger() -> None:
    """Reset the singleton WAF logger (useful for testing)."""
    global _waf_logger
    _waf_logger = None
