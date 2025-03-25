# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""CLI commands to manage app configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.server.commands.registry import command
from hop3.deploy import do_deploy
from hop3.lib import Abort, log

if TYPE_CHECKING:
    from hop3.orm import App


@command
class ConfigCmd:
    """Manage app config. Type 'hop config' for help."""


@command
class ConfigListCmd:
    """Show config."""

    name = "config:list"

    def run(self, app: App) -> None:
        env = app.get_runtime_env()
        for k, v in sorted(env.items()):
            log(f"{k}={v}", fg="white")


@command
class ConfigGetCmd:
    """e.g.: hop config:get <app> FOO."""

    name = "config:get"

    def add_arguments(self, parser) -> None:
        parser.add_argument("setting", type=str)

    def run(self, app: App, setting: str) -> None:
        env = app.get_runtime_env()
        if setting in env:
            log(f"{env[setting]}", fg="white")


@command
class ConfigSetCmd:
    """e.g.: hop config:set <app> FOO=bar BAZ=quux."""

    name = "config:set"

    def add_arguments(self, parser) -> None:
        parser.add_argument("settings", nargs="+")

    def run(self, app: App, settings: list[str]) -> None:
        env = app.get_runtime_env()

        for s in settings:
            key, value = self._parse_setting(s)
            log(f"Setting {key:s}={value} for '{app.name:s}'", fg="white")
            env[key] = value

        app.update_runtime_env(env)

        do_deploy(app)

    def _parse_setting(self, setting: str) -> tuple[str, str]:
        """Parse a configuration setting provided as a string.

        Input:
        - setting: A string representing a configuration setting in the format 'key=value'.

        Returns:
        - A tuple containing the key and value as strings, extracted from the input setting.
        """
        if "=" not in setting:
            msg = f"Error: malformed setting '{setting}'"
            raise Abort(msg)

        key, value = setting.split("=", 1)
        return key.strip(), value.strip()


@command
class ConfigUnsetCmd:
    """e.g.: hop config:unset <app> FOO."""

    name = "config:unset"

    def add_arguments(self, parser) -> None:
        parser.add_argument("settings", nargs="+")

    def run(self, app: App, settings: list[str]) -> None:
        env = app.get_runtime_env()

        for s in settings:
            if s in env:
                del env[s]
                log(f"Unsetting {s} for '{app.name}'")

        app.update_runtime_env(env)

        do_deploy(app)


@command
class ConfigLiveCmd:
    """e.g.: hop config:live <app>."""

    name = "config:live"

    def run(self, app: App) -> None:
        env = app.get_runtime_env()

        if not env:
            log(
                f"Warning: app '{app.name}' not deployed, no config found.",
                fg="yellow",
            )
            return

        for k, v in sorted(env.items()):
            log(f"{k}={v}", fg="white")
