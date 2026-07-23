# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Language toolchain for Elixir projects."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.lib import log

from ._base import LanguageToolchain

if TYPE_CHECKING:
    from hop3.core.protocols import BuildArtifact


class ElixirToolchain(LanguageToolchain):
    """
    Language toolchain for Elixir projects.

    This is responsible for building Elixir projects by checking for Mix
    (mix.exs) configuration files.
    """

    name = "Elixir"
    requirements = ["elixir", "mix"]  # ruff:ignore[mutable-class-default]

    def accept(self) -> bool:
        """Check if the application has Elixir/Mix configuration."""
        # Check for Mix project file
        return (self.src_path / "mix.exs").exists()

    def _get_mix_env(self) -> dict[str, str]:
        """
        Get environment variables for Mix/Hex/Rebar.

        Sets MIX_HOME and HEX_HOME to app-local directories so that
        Hex and rebar are installed per-app rather than globally.
        Also sets MIX_ENV to prod by default.

        Returns:
            Dict of environment variables for Mix commands.
        """
        mix_home = str(self.app_path / ".mix")
        hex_home = str(self.app_path / ".hex")
        return {
            "MIX_HOME": mix_home,
            "HEX_HOME": hex_home,
            "MIX_ENV": "prod",
        }

    def _install_hex_and_rebar(self, env: dict[str, str]) -> None:
        """
        Install Hex and rebar non-interactively.

        This ensures that Hex (the package manager) and rebar (the Erlang
        build tool) are available locally without interactive prompts.
        The --force flag suppresses the "Shall I install Hex?" prompt.

        Args:
            env: Environment variables including MIX_HOME and HEX_HOME.
        """
        log("Installing Hex package manager...", level=2, fg="cyan")
        self.shell("mix local.hex --force", env=env)

        log("Installing rebar build tool...", level=2, fg="cyan")
        self.shell("mix local.rebar --force", env=env)

    def build(self) -> BuildArtifact:
        """
        Build the Elixir application using Mix.

        This installs Hex and rebar, fetches dependencies, and compiles
        the application. MIX_HOME and HEX_HOME are set to app-local
        directories to avoid interactive prompts and global state.
        """
        log(f"Building Elixir application '{self.app_name}'", level=1, fg="blue")

        # Set up app-local Mix environment
        mix_env = self._get_mix_env()
        log(
            f"Using MIX_HOME={mix_env['MIX_HOME']}, HEX_HOME={mix_env['HEX_HOME']}",
            level=2,
            fg="cyan",
        )

        # Install Hex and rebar non-interactively (required before deps.get)
        self._install_hex_and_rebar(mix_env)

        # NOTE: do NOT wipe _build/ or deps/ here. Each deploy extracts a fresh
        # src tree (the upload extractor clears it first), so there's no stale
        # state to clean — and an app's `before-build` may already have produced
        # a production release in _build/prod/rel/ (Phoenix's `mix release`).
        # Deleting _build/ here erased that release, so the runtime's
        # `_build/prod/rel/<app>/bin/<app>` came up "not found".

        # Fetch dependencies
        log("Fetching Elixir dependencies...", level=2, fg="cyan")
        self.shell("mix deps.get", env=mix_env)

        # Compile the application
        log("Compiling Elixir application...", level=2, fg="cyan")
        result = self.shell("mix compile", env=mix_env, check=False)

        if result.returncode == 0:
            log("Elixir compilation successful", level=2, fg="green")
        else:
            log(
                "Elixir compilation failed - check mix.exs and source code",
                level=1,
                fg="red",
            )

        # Create runtime config with Mix env vars so they're available at runtime
        runtime = self._make_runtime_config(env_vars=mix_env)

        return self._make_build_artifact(kind="elixir", runtime=runtime)
