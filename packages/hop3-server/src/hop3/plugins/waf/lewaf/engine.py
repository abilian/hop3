# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""LeWAF engine implementation for Hop3.

This module provides the WafEngine protocol implementation using LeWAF,
a pure Python WAF engine with SecLang (ModSecurity) compatibility.

LeWAF Integration:
    LeWAF is imported as a hard dependency. The integration provides:
    - Request inspection using OWASP CRS rules
    - Per-app configuration via YAML files
    - Reverse proxy service running on Unix socket

    LeWAF runs as a separate proxy service (managed by Honcho/supervisor):
        Client -> Nginx -> LeWAF Proxy -> App Backend
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

# Import LeWAF components
# These imports verify lewaf is installed and provide access to WAF functionality
try:
    from lewaf.integration import WAF as LeWAFCore
    from lewaf.transaction import Transaction as LeWAFTransaction

    LEWAF_AVAILABLE = True
except ImportError:
    LEWAF_AVAILABLE = False
    LeWAFCore = None  # type: ignore[assignment, misc]
    LeWAFTransaction = None  # type: ignore[assignment, misc]

if TYPE_CHECKING:
    from hop3.core.protocols import WafConfig


def is_lewaf_available() -> bool:
    """Check if the LeWAF package is installed and available.

    Returns:
        True if lewaf package is installed and can be imported.
    """
    return LEWAF_AVAILABLE


class LeWafEngine:
    """LeWAF Web Application Firewall engine.

    Implements the WafEngine protocol to provide WAF protection for Hop3 apps.
    LeWAF runs as a separate HTTP proxy service, sitting between the reverse
    proxy (Nginx) and the application backends.

    Architecture:
        Client -> Nginx -> LeWAF (this engine) -> App Backend

    The engine manages:
    - LeWAF service lifecycle (start/stop/reload)
    - Per-app configuration generation
    - Upstream routing for protected apps
    - Audit logging configuration

    LeWAF Package:
        This engine requires the lewaf package to be installed.
        Use `is_lewaf_available()` to check availability before operations.
    """

    name = "lewaf"

    def __init__(self) -> None:
        """Initialize the LeWAF engine.

        Raises:
            RuntimeError: If lewaf package is not installed.
        """
        if not LEWAF_AVAILABLE:
            msg = "LeWAF package is not installed. Install it with: pip install lewaf"
            logger.error(msg)
            raise RuntimeError(msg)

        from hop3.config import HopConfig  # noqa: PLC0415

        config = HopConfig.get_instance()

        self._waf_root = config.WAF_ROOT
        self._config_dir = config.WAF_CONFIG
        self._apps_config_dir = config.WAF_APPS_CONFIG
        self._crs_dir = config.WAF_CRS
        self._log_dir = config.WAF_LOG
        self._socket_path = config.WAF_SOCKET

        # LeWAF core instance (lazily initialized)
        self._waf_core: LeWAFCore | None = None

        # Service state
        self._service: LeWafService | None = None

    @property
    def service(self) -> LeWafService:
        """Get or create the LeWAF service manager."""
        if self._service is None:
            self._service = LeWafService(
                waf_root=self._waf_root,
                config_dir=self._config_dir,
                socket_path=self._socket_path,
                log_dir=self._log_dir,
            )
        return self._service

    @property
    def waf_core(self) -> LeWAFCore:
        """Get or create the LeWAF core instance.

        The core instance is initialized with default settings.
        Per-app configurations are applied separately via YAML files
        that the LeWAF service reads.

        Returns:
            The LeWAF core instance for request inspection.
        """
        if self._waf_core is None:
            # Initialize LeWAF with default configuration
            # Per-app rules are loaded separately from YAML configs
            self._waf_core = LeWAFCore({})
            logger.debug("Initialized LeWAF core instance")
        return self._waf_core

    def get_version_info(self) -> dict:
        """Get LeWAF version and capability information.

        Returns:
            Dictionary with version info, capabilities, and status.
        """
        try:
            import lewaf  # noqa: PLC0415

            version = getattr(lewaf, "__version__", "unknown")
        except (ImportError, AttributeError):
            version = "unknown"

        return {
            "engine": "lewaf",
            "version": version,
            "available": LEWAF_AVAILABLE,
            "crs_dir": str(self._crs_dir),
            "config_dir": str(self._config_dir),
        }

    def start(self) -> None:
        """Start the LeWAF service.

        This starts the LeWAF proxy process if it's not already running.
        The service listens on a Unix socket for incoming requests from Nginx.
        """
        logger.info("Starting LeWAF service")
        self.service.start()

    def stop(self) -> None:
        """Stop the LeWAF service.

        Gracefully shuts down the LeWAF proxy process.
        """
        logger.info("Stopping LeWAF service")
        self.service.stop()

    def reload(self) -> None:
        """Reload the LeWAF configuration.

        Triggers a configuration reload without restarting the service.
        Uses file-touch mechanism to signal the service.
        """
        logger.info("Reloading LeWAF configuration")
        self.service.reload()

    def is_running(self) -> bool:
        """Check if the LeWAF service is running.

        Returns:
            True if the LeWAF process is running and responsive.
        """
        return self.service.is_running()

    def configure_app(self, waf_config: WafConfig) -> None:
        """Configure WAF protection for an application.

        Generates per-app configuration and adds routing rules to LeWAF.

        Args:
            waf_config: WAF configuration for the application.
        """
        if not waf_config.enabled:
            logger.debug(f"WAF disabled for app {waf_config.app_name}, skipping")
            return

        logger.info(f"Configuring WAF for app {waf_config.app_name}")
        config_generator = LeWafConfigGenerator(
            apps_config_dir=self._apps_config_dir,
            crs_dir=self._crs_dir,
        )
        config_generator.generate_app_config(waf_config)

        # Trigger reload if service is running
        if self.is_running():
            self.reload()

    def remove_app(self, app_name: str) -> None:
        """Remove WAF configuration for an application.

        Removes the app's configuration file and routing rules.

        Args:
            app_name: Name of the application to remove.
        """
        logger.info(f"Removing WAF configuration for app {app_name}")
        config_file = self._apps_config_dir / f"{app_name}.yaml"
        if config_file.exists():
            config_file.unlink()

        # Trigger reload if service is running
        if self.is_running():
            self.reload()

    def get_upstream_socket(self) -> str:
        """Get the Unix socket path for connecting to LeWAF.

        Returns:
            Path to the LeWAF Unix socket (e.g., /home/hop3/waf/lewaf.sock)
        """
        return str(self._socket_path)

    def get_app_upstream(self, app_name: str) -> str:
        """Get the upstream URL for an app through LeWAF.

        Args:
            app_name: Name of the application.

        Returns:
            Upstream URL for Nginx to connect to LeWAF for this app.
            Format: unix:/path/to/lewaf.sock
        """
        return f"unix:{self._socket_path}"


class LeWafService:
    """Manages the LeWAF service process.

    Handles starting, stopping, and reloading the LeWAF process.
    The service runs as a separate process managed by Honcho alongside
    hop3-server and uWSGI.
    """

    def __init__(
        self,
        waf_root: Path,
        config_dir: Path,
        socket_path: Path,
        log_dir: Path,
    ) -> None:
        """Initialize the service manager.

        Args:
            waf_root: Root directory for WAF files.
            config_dir: Directory containing WAF configuration.
            socket_path: Unix socket path for the service.
            log_dir: Directory for audit logs.
        """
        self._waf_root = waf_root
        self._config_dir = config_dir
        self._socket_path = socket_path
        self._log_dir = log_dir
        self._pidfile = waf_root / "lewaf.pid"
        self._reload_trigger = config_dir / ".reload"

    def start(self) -> None:
        """Start the LeWAF service.

        The service is started via Honcho/supervisord, not directly.
        This method ensures the configuration directories exist.
        """
        # Ensure directories exist
        self._waf_root.mkdir(parents=True, exist_ok=True)
        self._config_dir.mkdir(parents=True, exist_ok=True)
        self._log_dir.mkdir(parents=True, exist_ok=True)

        # TODO: Generate main config and start via honcho
        logger.info("LeWAF service directories initialized")

    def stop(self) -> None:
        """Stop the LeWAF service.

        The service is stopped via Honcho/supervisord.
        """
        # TODO: Implement graceful shutdown via honcho
        logger.info("LeWAF service stop requested")

    def reload(self) -> None:
        """Reload the LeWAF configuration.

        Uses file-touch mechanism to signal configuration reload.
        """
        self._reload_trigger.touch()
        logger.debug(f"Touched reload trigger: {self._reload_trigger}")

    def is_running(self) -> bool:
        """Check if the LeWAF service is running.

        Returns:
            True if the service PID file exists and process is running.
        """
        if not self._pidfile.exists():
            return False

        try:
            pid = int(self._pidfile.read_text().strip())
            # Check if process is running (send signal 0)
            import os

            os.kill(pid, 0)
            return True
        except (ValueError, ProcessLookupError, PermissionError):
            return False


class LeWafConfigGenerator:
    """Generates LeWAF configuration files.

    Creates YAML configuration files for LeWAF based on app settings
    from hop3.toml [waf] and [security.rules] sections.
    """

    def __init__(self, apps_config_dir: Path, crs_dir: Path) -> None:
        """Initialize the config generator.

        Args:
            apps_config_dir: Directory for per-app config files.
            crs_dir: Directory containing OWASP CRS rules.
        """
        self._apps_config_dir = apps_config_dir
        self._crs_dir = crs_dir

    def generate_app_config(self, waf_config: WafConfig) -> Path:
        """Generate configuration file for an application.

        Args:
            waf_config: WAF configuration for the app.

        Returns:
            Path to the generated configuration file.
        """
        import yaml  # noqa: PLC0415

        self._apps_config_dir.mkdir(parents=True, exist_ok=True)

        config = {
            "app_name": waf_config.app_name,
            "enabled": waf_config.enabled,
            "mode": waf_config.mode,
            "paranoia_level": waf_config.paranoia_level,
            "ruleset": waf_config.ruleset,
            "rules": {
                "allow_paths": waf_config.allow_paths,
                "deny_paths": waf_config.deny_paths,
                "allow_ips": waf_config.allow_ips,
                "deny_ips": waf_config.deny_ips,
                "exclusions": waf_config.exclusions,
                "disabled_rule_ids": waf_config.disabled_rules,
            },
        }

        if waf_config.custom_rules:
            config["custom_rules"] = waf_config.custom_rules

        config_file = self._apps_config_dir / f"{waf_config.app_name}.yaml"
        with config_file.open("w") as f:
            yaml.safe_dump(config, f, default_flow_style=False)

        logger.debug(f"Generated WAF config: {config_file}")
        return config_file
