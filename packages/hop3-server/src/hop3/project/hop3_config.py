# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Parser for hop3.toml configuration files.

This module implements parsing for the hop3.toml configuration format as defined
in ADR-001 and ADR-002. It supports the "Convention over Configuration" principle
by making hop3.toml optional and providing sensible defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomllib  # Python 3.11+


@dataclass
class Hop3Config:
    """Represents a parsed hop3.toml configuration file.

    This class provides access to all sections of the hop3.toml file,
    with a focus on the [run] and [build] sections that overlap with
    Procfile functionality.
    """

    # Raw parsed TOML data
    _data: dict[str, Any] = field(default_factory=dict)

    # Parsed path
    config_path: Path | None = None

    @classmethod
    def from_file(cls, filename: str | Path) -> Hop3Config:
        """Load and parse a hop3.toml file.

        Args:
            filename: Path to the hop3.toml file

        Returns:
            Hop3Config instance with parsed data

        Raises:
            FileNotFoundError: If the file doesn't exist
            TOMLDecodeError: If the file is not valid TOML
        """
        path = Path(filename)
        if not path.exists():
            msg = f"File not found: {filename}"
            raise FileNotFoundError(msg)

        with path.open("rb") as f:
            data = tomllib.load(f)

        return cls(_data=data, config_path=path)

    @classmethod
    def from_str(cls, content: str) -> Hop3Config:
        """Parse hop3.toml content from a string.

        Args:
            content: TOML content as string

        Returns:
            Hop3Config instance with parsed data
        """
        data = tomllib.loads(content)
        return cls(_data=data)

    # =========================================================================
    # [metadata] section
    # =========================================================================

    @property
    def metadata(self) -> dict[str, Any]:
        """Get the [metadata] section."""
        return self._data.get("metadata", {})

    @property
    def app_id(self) -> str | None:
        """Get metadata.id (unique identifier)."""
        return self.metadata.get("id")

    @property
    def version(self) -> str | None:
        """Get metadata.version."""
        return self.metadata.get("version")

    @property
    def title(self) -> str | None:
        """Get metadata.title."""
        return self.metadata.get("title")

    # =========================================================================
    # [build] section
    # =========================================================================

    @property
    def build(self) -> dict[str, Any]:
        """Get the [build] section."""
        return self._data.get("build", {})

    @property
    def build_commands(self) -> list[str]:
        """Get build.build commands (list of shell commands for building).

        Returns:
            List of build commands, empty list if not specified
        """
        build_cmds = self.build.get("build", [])
        # Normalize to list
        if isinstance(build_cmds, str):
            return [build_cmds]
        return build_cmds if isinstance(build_cmds, list) else []

    @property
    def before_build_commands(self) -> list[str]:
        """Get build.before-build commands.

        Returns:
            List of commands to run before build
        """
        cmds = self.build.get("before-build", [])
        if isinstance(cmds, str):
            return [cmds]
        return cmds if isinstance(cmds, list) else []

    @property
    def test_commands(self) -> list[str]:
        """Get build.test commands (smoke tests).

        Returns:
            List of test commands
        """
        test_cmds = self.build.get("test", [])
        if isinstance(test_cmds, str):
            return [test_cmds]
        return test_cmds if isinstance(test_cmds, list) else []

    @property
    def build_packages(self) -> list[str]:
        """Get build.packages (system packages for build)."""
        return self.build.get("packages", [])

    @property
    def pip_install(self) -> list[str]:
        """Get build.pip-install (Python packages to install)."""
        return self.build.get("pip-install", [])

    # =========================================================================
    # [run] section - Maps to Procfile workers
    # =========================================================================

    @property
    def run(self) -> dict[str, Any]:
        """Get the [run] section."""
        return self._data.get("run", {})

    @property
    def run_packages(self) -> list[str]:
        """Get run.packages (system packages for runtime)."""
        return self.run.get("packages", [])

    @property
    def before_run_commands(self) -> list[str]:
        """Get run.before-run commands.

        Returns:
            List of commands to run before starting the app
        """
        cmds = self.run.get("before-run", [])
        if isinstance(cmds, str):
            return [cmds]
        return cmds if isinstance(cmds, list) else []

    @property
    def start_command(self) -> str | list[str] | None:
        """Get run.start command(s).

        This maps to the primary process in a Procfile (usually 'web').

        Returns:
            Start command(s), or None if not specified
        """
        return self.run.get("start")

    def get_workers_from_run_section(self) -> dict[str, str]:
        """Extract worker definitions from [run] section.

        This provides Procfile-compatible worker definitions from hop3.toml.
        Currently supports:
        - run.start -> 'web' worker
        - run.before-run -> 'prerun' worker
        - Future: run.workers.* -> named workers

        Returns:
            Dictionary mapping worker names to commands
        """
        workers = {}

        # Map run.start to 'web' worker
        start_cmd = self.start_command
        if start_cmd:
            if isinstance(start_cmd, list):
                # Join multiple commands with &&
                workers["web"] = " && ".join(start_cmd)
            else:
                workers["web"] = start_cmd

        # Map run.before-run to 'prerun' worker
        before_run = self.before_run_commands
        if before_run:
            workers["prerun"] = " && ".join(before_run)

        # Map build.before-build to 'prebuild' worker
        before_build = self.before_build_commands
        if before_build:
            workers["prebuild"] = " && ".join(before_build)

        return workers

    # =========================================================================
    # [env] section
    # =========================================================================

    @property
    def env(self) -> dict[str, Any]:
        """Get the [env] section (environment variables)."""
        return self._data.get("env", {})

    # =========================================================================
    # [port] section
    # =========================================================================

    @property
    def port(self) -> dict[str, Any]:
        """Get the [port] section."""
        return self._data.get("port", {})

    # =========================================================================
    # [[provider]] section
    # =========================================================================

    @property
    def providers(self) -> list[dict[str, Any]]:
        """Get the [[provider]] sections (list of service providers)."""
        return self._data.get("provider", [])

    # =========================================================================
    # [waf] section - Web Application Firewall configuration
    # =========================================================================

    @property
    def waf(self) -> dict[str, Any]:
        """Get the [waf] section."""
        return self._data.get("waf", {})

    @property
    def waf_enabled(self) -> bool:
        """Check if WAF is enabled for this application."""
        return self.waf.get("enabled", False)

    @property
    def waf_engine(self) -> str:
        """Get the WAF engine (lewaf, coraza)."""
        return self.waf.get("engine", "lewaf")

    @property
    def waf_ruleset(self) -> str:
        """Get the WAF ruleset (owasp-crs, minimal, none)."""
        return self.waf.get("ruleset", "owasp-crs")

    @property
    def waf_paranoia_level(self) -> int:
        """Get the CRS paranoia level (1-4)."""
        return self.waf.get("paranoia_level", 1)

    @property
    def waf_mode(self) -> str:
        """Get the WAF mode (block, detect)."""
        return self.waf.get("mode", "block")

    @property
    def waf_exclusions(self) -> dict[str, Any]:
        """Get the [waf.exclusions] section."""
        return self.waf.get("exclusions", {})

    @property
    def waf_crs(self) -> dict[str, Any]:
        """Get the [waf.crs] section for custom CRS rules."""
        return self.waf.get("crs", {})

    # =========================================================================
    # [security.rules] section - Simple allow/deny rules
    # =========================================================================

    @property
    def security(self) -> dict[str, Any]:
        """Get the [security] section."""
        return self._data.get("security", {})

    @property
    def security_rules(self) -> dict[str, Any]:
        """Get the [security.rules] section."""
        return self.security.get("rules", {})

    @property
    def security_allow_paths(self) -> list[str]:
        """Get paths that bypass WAF inspection."""
        return self.security_rules.get("allow", [])

    @property
    def security_deny_paths(self) -> list[str]:
        """Get paths that are blocked before WAF inspection."""
        return self.security_rules.get("deny", [])

    @property
    def security_allow_ips(self) -> list[str]:
        """Get IPs that bypass all security checks."""
        return self.security_rules.get("allow_ips", [])

    @property
    def security_deny_ips(self) -> list[str]:
        """Get IPs that are blocked at WAF level."""
        return self.security_rules.get("deny_ips", [])

    def get_waf_config(self, app_name: str) -> dict[str, Any]:
        """Build a complete WAF configuration dict for this application.

        This combines [waf] and [security.rules] sections into a single
        configuration object that can be used by the WAF engine.

        Args:
            app_name: Name of the application.

        Returns:
            Dictionary with all WAF configuration for this app.
        """
        return {
            "app_name": app_name,
            "enabled": self.waf_enabled,
            "engine": self.waf_engine,
            "ruleset": self.waf_ruleset,
            "paranoia_level": self.waf_paranoia_level,
            "mode": self.waf_mode,
            "exclusions": self.waf_exclusions.get("paths", []),
            "disabled_rules": self.waf_exclusions.get("rule_ids", []),
            "custom_rules": self.waf_crs.get("custom", ""),
            "allow_paths": self.security_allow_paths,
            "deny_paths": self.security_deny_paths,
            "allow_ips": self.security_allow_ips,
            "deny_ips": self.security_deny_ips,
        }

    # =========================================================================
    # Utility methods
    # =========================================================================

    def has_section(self, section_name: str) -> bool:
        """Check if a section exists in the configuration.

        Args:
            section_name: Name of the section (e.g., 'run', 'build')

        Returns:
            True if the section exists and is not empty
        """
        return section_name in self._data and bool(self._data[section_name])

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary with all configuration data
        """
        return {
            "config_path": str(self.config_path) if self.config_path else None,
            "metadata": self.metadata,
            "build": self.build,
            "run": self.run,
            "env": self.env,
            "port": self.port,
            "providers": self.providers,
            "workers": self.get_workers_from_run_section(),
        }

    def __repr__(self) -> str:
        if self.config_path:
            return f"<Hop3Config {self.config_path}>"
        return "<Hop3Config from_str>"
