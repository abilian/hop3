# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Runtime manifest builder - consolidates Procfile and hop3.toml into RuntimeConfig.

This module implements the merge logic that combines multiple configuration
sources (Procfile, hop3.toml) into a single RuntimeConfig that is stored
in the build artifact.

The key principle is that after this merge, the run phase only needs to
look at the artifact - no more parsing of Procfile or hop3.toml at runtime.

Example usage:
    from hop3.core.manifest import RuntimeManifestBuilder
    from hop3.project.config import AppConfig

    app_config = AppConfig.from_dir(app_dir)
    builder = RuntimeManifestBuilder(app_config)
    runtime_config = builder.build(
        env_vars={"PYTHONPATH": "/app/src"},
        path_prepend=["/app/venv/bin"],
        working_dir="/app",
    )
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.core.artifacts import RuntimeConfig

if TYPE_CHECKING:
    from hop3.project.config import AppConfig


class RuntimeManifestBuilder:
    """
    Builds RuntimeConfig by merging Procfile and hop3.toml.

    This class implements the single merge point for all runtime configuration.
    It follows the precedence: hop3.toml > Procfile > defaults.
    """

    def __init__(self, app_config: AppConfig) -> None:
        """
        Initialize the builder with an AppConfig.

        Args:
            app_config: Parsed application configuration (Procfile + hop3.toml)
        """
        self.app_config = app_config

    def build(
        self,
        env_vars: dict[str, str] | None = None,
        path_prepend: list[str] | None = None,
        working_dir: str = "",
        workers: dict[str, str] | None = None,
    ) -> RuntimeConfig:
        """
        Build RuntimeConfig by merging all configuration sources.

        Args:
            env_vars: Environment variables from toolchain (absolute paths)
            path_prepend: Paths to prepend to PATH from toolchain
            working_dir: Working directory for processes
            workers: Worker definitions from builder (takes precedence over Procfile)

        Returns:
            Complete RuntimeConfig with all fields populated
        """
        # Start with toolchain-provided values
        merged_env = dict(env_vars) if env_vars else {}
        merged_paths = list(path_prepend) if path_prepend else []

        # Add environment variables from hop3.toml [env] section
        if self.app_config.has_hop3_toml:
            hop3_env = self.app_config.hop3_config.env
            for key, value in hop3_env.items():
                # Toolchain env vars take precedence (they have absolute paths)
                if key not in merged_env:
                    merged_env[key] = str(value)

        # Determine workers with precedence:
        # 1. Procfile (base — convention/auto-detected)
        # 2. Builder-provided workers (override — e.g., NixBuilder's runtime.json)
        # 3. hop3.toml [run] section (highest — explicit user config)
        #
        # Each layer overrides matching keys from the previous layer,
        # but non-conflicting workers are preserved (e.g., Procfile's
        # "worker" is kept even when hop3.toml overrides "web").
        merged_workers = self._get_workers()  # Start with Procfile

        if workers:
            merged_workers.update(workers)  # Builder overrides

        if self.app_config.has_hop3_toml:
            hop3_workers = self.app_config.hop3_config.get_workers_from_run_section()
            lifecycle_hooks = {"prebuild", "postbuild", "prerun"}
            hop3_workers = {
                k: v for k, v in hop3_workers.items() if k not in lifecycle_hooks
            }
            if hop3_workers:
                merged_workers.update(hop3_workers)  # hop3.toml overrides

        # Get before-run commands
        before_run = self._get_before_run()

        # Get static paths
        static_paths = self._get_static_paths()

        # Get healthcheck configuration
        healthcheck_path = ""
        healthcheck_timeout = 30
        if self.app_config.has_hop3_toml:
            healthcheck_path = self.app_config.hop3_config.healthcheck_path
            healthcheck_timeout = self.app_config.hop3_config.healthcheck_timeout

        return RuntimeConfig(
            env_vars=merged_env,
            path_prepend=merged_paths,
            working_dir=working_dir,
            workers=merged_workers,
            before_run=before_run,
            static_paths=static_paths,
            healthcheck_path=healthcheck_path,
            healthcheck_timeout=healthcheck_timeout,
        )

    def _get_workers(self) -> dict[str, str]:
        """
        Get merged worker definitions.

        Excludes lifecycle hooks (prebuild, postbuild, prerun) which are
        handled separately.

        Returns:
            Dictionary mapping worker names to commands
        """
        all_workers = self.app_config.workers

        # Filter out lifecycle hooks - they're not persistent workers
        lifecycle_hooks = {"prebuild", "postbuild", "prerun"}
        return {
            name: cmd
            for name, cmd in all_workers.items()
            if name not in lifecycle_hooks
        }

    def _get_before_run(self) -> list[str]:
        """
        Get before-run commands.

        Combines:
        1. hop3.toml [run] before-run (list)
        2. Procfile prerun (single command)

        Returns:
            List of commands to run before starting workers
        """
        commands = []

        # hop3.toml before-run commands (higher precedence)
        if self.app_config.has_hop3_toml:
            commands.extend(self.app_config.hop3_config.before_run_commands)

        # Procfile prerun (only if no hop3.toml before-run)
        if not commands:
            prerun = self.app_config.procfile.workers.get("prerun", "")
            if prerun:
                commands.append(prerun)

        return commands

    def _get_static_paths(self) -> dict[str, str]:
        """
        Get static file path mappings.

        Returns:
            Dictionary mapping URL paths to filesystem paths
        """
        if self.app_config.has_hop3_toml:
            return self.app_config.hop3_config.static_paths
        return {}
