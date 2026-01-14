# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Server-side logging for Hop3.

This module provides structured logging for debugging server operations.
Logs are written to both the console (via the existing log() function)
and to a persistent log file with automatic rotation.

Usage:
    from hop3.lib.logging import server_log

    server_log.info("Deploying app", app_name="myapp")
    server_log.debug("Loaded env_vars", count=5, vars={"HOST_NAME": "..."})
    server_log.error("Deployment failed", app_name="myapp", error=str(e))

Log files are stored in HOP3_ROOT/log/server.log (default: /home/hop3/log/server.log)

Configuration via hop3-server.toml or environment variables:
    HOP3_LOG_LEVEL: DEBUG, INFO (default), WARNING, ERROR
    HOP3_LOG_MAX_MB: Max file size before rotation (default: 10)
    HOP3_LOG_BACKUP_COUNT: Number of old log files to keep (default: 5)

With defaults, keeps up to 60MB of logs (10MB current + 5 x 10MB backups).
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

# Import config module - may fail during early bootstrap
try:
    from hop3 import config as hop3_config
except ImportError:
    hop3_config = None  # type: ignore[assignment]


def _get_log_level() -> str:
    """Get log level from config or environment.

    Priority: environment variable > config file > default (INFO)
    """
    # Check environment first (highest priority)
    if os.environ.get("HOP3_LOG_LEVEL"):
        return os.environ["HOP3_LOG_LEVEL"].upper()

    # Try to read from config
    if hop3_config is not None:
        try:
            return hop3_config.config.HOP3_LOG_LEVEL
        except Exception:
            pass

    return "INFO"


def _get_log_dir() -> Path:
    """Get log directory from config or environment."""
    if hop3_config is not None:
        try:
            return hop3_config.config.HOP3_ROOT / "log"
        except Exception:
            pass
    return Path(os.environ.get("HOP3_ROOT", "/home/hop3")) / "log"


# Default log location (computed at import time, but configure() uses fresh values)
DEFAULT_LOG_DIR = _get_log_dir()
DEFAULT_LOG_FILE = DEFAULT_LOG_DIR / "server.log"

# Log rotation settings (still from environment - these are advanced options)
# Default: 10MB
LOG_MAX_BYTES = int(os.environ.get("HOP3_LOG_MAX_MB", "10")) * 1024 * 1024
# Default: keep 5 old files
LOG_BACKUP_COUNT = int(os.environ.get("HOP3_LOG_BACKUP_COUNT", "5"))


class ServerLogger:
    """Structured logger for Hop3 server operations.

    Provides methods for logging at different levels with structured data.
    Automatically includes timestamps and formats messages consistently.
    """

    def __init__(self, name: str = "hop3.server"):
        self.logger = logging.getLogger(name)
        self._configured = False

    def configure(self, log_file: Path | None = None, level: str | None = None) -> None:
        """Configure the logger with file and console handlers.

        Args:
            log_file: Path to log file (default: HOP3_ROOT/log/server.log)
            level: Log level (DEBUG, INFO, WARNING, ERROR)
        """
        if self._configured:
            return

        # Use fresh values from config/environment
        log_file = log_file or (_get_log_dir() / "server.log")
        level = level or _get_log_level()

        # Ensure log directory exists
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # Set level
        self.logger.setLevel(getattr(logging, level, logging.INFO))

        # File handler with automatic rotation
        # Rotates when file reaches LOG_MAX_BYTES, keeps LOG_BACKUP_COUNT old files
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)  # File gets everything
        file_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)

        # Only add stderr handler if not in test mode
        if "PYTEST_VERSION" not in os.environ:
            stderr_handler = logging.StreamHandler()
            stderr_handler.setLevel(logging.WARNING)  # Console only gets warnings+
            stderr_handler.setFormatter(file_formatter)
            self.logger.addHandler(stderr_handler)

        self._configured = True
        self.logger.info(
            "Hop3 server logging initialized", extra={"log_file": str(log_file)}
        )

    def _format_message(self, msg: str, **kwargs: Any) -> str:
        """Format message with key=value pairs."""
        if not kwargs:
            return msg
        pairs = " ".join(f"{k}={v!r}" for k, v in kwargs.items())
        return f"{msg} | {pairs}"

    def debug(self, msg: str, **kwargs: Any) -> None:
        """Log debug message (verbose, for troubleshooting)."""
        self._ensure_configured()
        self.logger.debug(self._format_message(msg, **kwargs))

    def info(self, msg: str, **kwargs: Any) -> None:
        """Log info message (normal operations)."""
        self._ensure_configured()
        self.logger.info(self._format_message(msg, **kwargs))

    def warning(self, msg: str, **kwargs: Any) -> None:
        """Log warning message (something unexpected but not fatal)."""
        self._ensure_configured()
        self.logger.warning(self._format_message(msg, **kwargs))

    def error(self, msg: str, **kwargs: Any) -> None:
        """Log error message (operation failed)."""
        self._ensure_configured()
        self.logger.error(self._format_message(msg, **kwargs))

    def exception(self, msg: str, **kwargs: Any) -> None:
        """Log error with exception traceback (call from within except block)."""
        self._ensure_configured()
        # noqa: LOG014 - this method is designed to be called from within except blocks
        self.logger.error(self._format_message(msg, **kwargs), exc_info=True)  # noqa: LOG014

    def _ensure_configured(self) -> None:
        """Ensure logger is configured before use."""
        if not self._configured:
            self.configure()


# Global server logger instance
server_log = ServerLogger()


# Convenience function to view recent logs
def get_recent_logs(lines: int = 100) -> list[str]:
    """Read recent log entries from the server log file.

    Args:
        lines: Number of lines to return

    Returns:
        List of log lines (most recent last)
    """
    if not DEFAULT_LOG_FILE.exists():
        return []

    with Path(DEFAULT_LOG_FILE).open() as f:
        all_lines = f.readlines()
        return all_lines[-lines:]
