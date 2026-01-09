# Copyright (c) 2024-2025, Abilian SAS
# ruff: noqa: N802
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, ClassVar

from hop3.lib.config import Config as ConfigLoader


class HopConfig:
    """Hop3 configuration with lazy evaluation and testability.

    This class provides:
    - Lazy property evaluation (derived values auto-update)
    - Dependency injection support for testing
    - Type-safe configuration access
    - Backward compatibility with module-level access

    Usage:
        # In production code
        from hop3.config import config
        app_path = config.APP_ROOT / "myapp"

        # In tests
        test_config = HopConfig(hop3_root=tmp_path)
        app = App(name="test", config=test_config)
    """

    # Class variable for global singleton instance
    _instance: ClassVar[HopConfig | None] = None

    def __init__(
        self,
        config_loader: ConfigLoader | None = None,
        hop3_root: Path | str | None = None,
    ):
        """Initialize configuration.

        Args:
            config_loader: Optional ConfigLoader instance (for file-based config)
            hop3_root: Optional override for HOP3_ROOT (useful for testing)
        """
        self._config_loader = config_loader or self._create_default_loader()
        self._hop3_root_override = Path(hop3_root) if hop3_root else None

    @staticmethod
    def _create_default_loader() -> ConfigLoader:
        """Create default config loader."""
        testing = "PYTEST_VERSION" in os.environ

        if not testing:
            hop3_root = Path(os.environ.get("HOP3_ROOT", "/home/hop3"))
            config_file = hop3_root / "hop3-server.toml"
            if config_file.exists():
                return ConfigLoader(file=config_file)

        # Testing mode or no config file
        loader = ConfigLoader()

        # Set test defaults
        if testing:
            os.environ.setdefault("HOP3_ROOT", "/tmp/hop3")
            os.environ.setdefault("ACME_ENGINE", "self-signed")
            os.environ.setdefault("ACME_EMAIL", "test@example.com")

        return loader

    # Base Configuration Properties

    @property
    def HOP3_ROOT(self) -> Path:
        """Root directory for all Hop3 data."""
        if self._hop3_root_override:
            return self._hop3_root_override
        return self._config_loader.get_path("HOP3_ROOT", "/home/hop3")

    @property
    def HOP3_USER(self) -> str:
        """System user running Hop3."""
        return self._config_loader.get_str("HOP3_USER", "hop3")

    @property
    def MODE(self) -> str:
        """Operating mode: production, development, testing."""
        return self._config_loader.get_str("MODE", "production")

    @property
    def HOP3_DEBUG(self) -> bool:
        """Enable debug mode."""
        return self._config_loader.get_bool("HOP3_DEBUG", default=False)

    # Security Configuration

    @property
    def HOP3_SECRET_KEY(self) -> str:
        """Secret key for session encryption."""
        return self._config_loader.get_str("HOP3_SECRET_KEY", "")

    @property
    def HOP3_TOKEN_EXPIRY_HOURS(self) -> int:
        """JWT token expiry in hours."""
        return self._config_loader.get_int("HOP3_TOKEN_EXPIRY_HOURS", 24)

    @property
    def HOP3_UNSAFE(self) -> bool:
        """UNSAFE MODE: Disables authentication. USE ONLY FOR TESTING."""
        return self._config_loader.get_bool("HOP3_UNSAFE", default=False)

    # Logging Configuration

    @property
    def HOP3_LOG_LEVEL(self) -> str:
        """Log level: DEBUG, INFO (default), WARNING, ERROR."""
        return self._config_loader.get_str("HOP3_LOG_LEVEL", "INFO").upper()

    # Proxy Configuration

    @property
    def HOP3_PROXY_TYPE(self) -> str:
        """Reverse proxy type: nginx, caddy, traefik."""
        return self._config_loader.get_str("HOP3_PROXY_TYPE", "nginx")

    # ACME Configuration

    @property
    def ACME_ENGINE(self) -> str:
        """ACME client engine: certbot, self-signed."""
        testing = "PYTEST_VERSION" in os.environ
        default = "self-signed" if testing else "certbot"
        return self._config_loader.get_str("ACME_ENGINE", default)

    @property
    def ACME_ROOT_CA(self) -> str:
        """ACME root certificate authority."""
        return self._config_loader.get_str("ACME_ROOT_CA", "letsencrypt.org")

    @property
    def ACME_EMAIL(self) -> str:
        """Email for ACME registration."""
        testing = "PYTEST_VERSION" in os.environ
        default = "test@example.com" if testing else "fixme@example.com"
        return self._config_loader.get_str("ACME_EMAIL", default)

    # Derived Paths (Lazy Evaluation)

    @property
    def HOP3_BIN(self) -> Path:
        """Binary directory."""
        return self.HOP3_ROOT / "bin"

    @property
    def HOP3_SCRIPT(self) -> str:
        """Path to hop3-server script (used for SSH forced commands and git hooks)."""
        return str(self.HOP3_ROOT / "venv" / "bin" / "hop3-server")

    @property
    def APP_ROOT(self) -> Path:
        """Root directory for all applications."""
        return self.HOP3_ROOT / "apps"

    @property
    def BACKUP_ROOT(self) -> Path:
        """Root directory for backups."""
        return self.HOP3_ROOT / "backups"

    @property
    def NGINX_ROOT(self) -> Path:
        """Nginx configuration directory."""
        return self.HOP3_ROOT / "nginx"

    @property
    def CACHE_ROOT(self) -> Path:
        """Cache directory."""
        return self.HOP3_ROOT / "cache"

    @property
    def CADDY_ROOT(self) -> Path:
        """Caddy configuration directory."""
        return self.HOP3_ROOT / "caddy"

    @property
    def TRAEFIK_ROOT(self) -> Path:
        """Traefik configuration directory."""
        return self.HOP3_ROOT / "traefik"

    @property
    def UWSGI_ROOT(self) -> Path:
        """uWSGI configuration root."""
        return self.HOP3_ROOT / "uwsgi"

    @property
    def UWSGI_AVAILABLE(self) -> Path:
        """uWSGI available configurations."""
        return self.HOP3_ROOT / "uwsgi-available"

    @property
    def UWSGI_ENABLED(self) -> Path:
        """uWSGI enabled configurations."""
        return self.HOP3_ROOT / "uwsgi-enabled"

    @property
    def UWSGI_LOG_MAXSIZE(self) -> str:
        """uWSGI log max size."""
        return "1048576"

    @property
    def ACME_WWW(self) -> Path:
        """ACME challenge directory."""
        return self.HOP3_ROOT / "acme"

    @property
    def ROOT_DIRS(self) -> list[Path]:
        """All root directories that should be created on setup."""
        return [
            self.APP_ROOT,
            self.BACKUP_ROOT,
            self.CACHE_ROOT,
            self.UWSGI_ROOT,
            self.UWSGI_AVAILABLE,
            self.UWSGI_ENABLED,
            self.NGINX_ROOT,
        ]

    # Constants

    @property
    def CRON_REGEXP(self) -> str:
        """Regular expression for cron job parsing."""
        return (
            r"^((?:(?:\*\/)?\d+)|\*) "
            r"((?:(?:\*\/)?\d+)|\*) "
            r"((?:(?:\*\/)?\d+)|\*) "
            r"((?:(?:\*\/)?\d+)|\*) "
            r"((?:(?:\*\/)?\d+)|\*) "
            r"(.*)$"
        )

    @property
    def TESTING(self) -> bool:
        """Check if running in test mode."""
        return "PYTEST_VERSION" in os.environ

    # Utility Methods

    def get_parameters(self) -> dict[str, Any]:
        """Get all configuration parameters as a dict.

        Useful for debugging and introspection.
        """
        return {
            name: getattr(self, name)
            for name in dir(self)
            if name.isupper() and not name.startswith("_")
        }

    @classmethod
    def get_instance(cls) -> HopConfig:
        """Get or create the global singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def set_instance(cls, instance: HopConfig) -> None:
        """Set the global singleton instance (useful for testing)."""
        cls._instance = instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the global singleton (useful for testing)."""
        cls._instance = None


# Global singleton instance
config = HopConfig.get_instance()


# Explicit module-level exports for type checking
# Type checkers will see these as real module attributes with proper types
# They are evaluated once at import time, but __getattr__ provides dynamic access
# For testing, use HopConfig.set_instance() to update the singleton

# Base Configuration
HOP3_ROOT: Path = config.HOP3_ROOT
HOP3_USER: str = config.HOP3_USER
HOP3_BIN: Path = config.HOP3_BIN
HOP3_SCRIPT: str = config.HOP3_SCRIPT
HOP3_DEBUG: bool = config.HOP3_DEBUG
HOP3_SECRET_KEY: str = config.HOP3_SECRET_KEY
HOP3_TOKEN_EXPIRY_HOURS: int = config.HOP3_TOKEN_EXPIRY_HOURS
HOP3_UNSAFE: bool = config.HOP3_UNSAFE
HOP3_LOG_LEVEL: str = config.HOP3_LOG_LEVEL
HOP3_PROXY_TYPE: str = config.HOP3_PROXY_TYPE
MODE: str = config.MODE

# Paths
APP_ROOT: Path = config.APP_ROOT
BACKUP_ROOT: Path = config.BACKUP_ROOT
NGINX_ROOT: Path = config.NGINX_ROOT
CADDY_ROOT: Path = config.CADDY_ROOT
TRAEFIK_ROOT: Path = config.TRAEFIK_ROOT
CACHE_ROOT: Path = config.CACHE_ROOT
UWSGI_ROOT: Path = config.UWSGI_ROOT
UWSGI_AVAILABLE: Path = config.UWSGI_AVAILABLE
UWSGI_ENABLED: Path = config.UWSGI_ENABLED
UWSGI_LOG_MAXSIZE: str = config.UWSGI_LOG_MAXSIZE

# ACME Configuration
ACME_ENGINE: str = config.ACME_ENGINE
ACME_ROOT_CA: str = config.ACME_ROOT_CA
ACME_EMAIL: str = config.ACME_EMAIL
ACME_WWW: Path = config.ACME_WWW

# Constants
CRON_REGEXP: str = config.CRON_REGEXP
ROOT_DIRS: list[Path] = config.ROOT_DIRS
TESTING: bool = config.TESTING

# Explicit exports for type checking and import discovery
__all__ = [  # noqa: RUF022
    # Class and instance
    "HopConfig",
    "config",
    # Base configuration
    "HOP3_ROOT",
    "HOP3_USER",
    "HOP3_BIN",
    "HOP3_SCRIPT",
    "HOP3_DEBUG",
    "HOP3_SECRET_KEY",
    "HOP3_TOKEN_EXPIRY_HOURS",
    "HOP3_UNSAFE",
    "HOP3_LOG_LEVEL",
    "HOP3_PROXY_TYPE",
    "MODE",
    # Paths
    "APP_ROOT",
    "BACKUP_ROOT",
    "NGINX_ROOT",
    "CADDY_ROOT",
    "TRAEFIK_ROOT",
    "CACHE_ROOT",
    "UWSGI_ROOT",
    "UWSGI_AVAILABLE",
    "UWSGI_ENABLED",
    "UWSGI_LOG_MAXSIZE",
    # ACME
    "ACME_ENGINE",
    "ACME_ROOT_CA",
    "ACME_EMAIL",
    "ACME_WWW",
    # Constants
    "CRON_REGEXP",
    "ROOT_DIRS",
    "TESTING",
    # Utility functions
    "get_parameters",
]


# Backward compatibility: module-level constants
# These delegate to the config object for lazy evaluation
# New code should use: from hop3.config import config
def get_parameters():
    """Get all configuration parameters (backward compatibility)."""
    return {k: v for k, v in globals().items() if re.match(r"[A-Z0-9_]+$", k)}


# Module-level __getattr__ to make "constants" dynamically read from config singleton
# This ensures that when tests update the config singleton, the module-level
# constants also reflect the new values
def __getattr__(name: str):
    """Dynamic attribute lookup for backward compatibility.

    This allows code to use `from hop3.config import APP_ROOT` and have it
    automatically use the current config singleton value, even if the singleton
    changes during testing.
    """
    cfg = HopConfig.get_instance()
    if hasattr(cfg, name):
        return getattr(cfg, name)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
