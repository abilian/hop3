# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands to manage app configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.deploy import do_deploy
from hop3.util import Abort, log
from hop3.util.settings import write_settings

from ._base import Cmd, command

if TYPE_CHECKING:
    from hop3.core.app import App


@command
class ConfigCmd(Cmd):
    """Show config, e.g.: hop config <app>."""

    def add_arguments(self, parser) -> None:
        parser.add_argument("app", type=str)

    def run(self, app: App) -> None:
        env = app.get_runtime_env()
        for k, v in sorted(env.items()):
            log(f"{k}={v}", fg="white")


# @hop3.command("config:get")
# @argument("app", type=AppParamType())
# @argument("setting")
# def cmd_config_get(app: App, setting) -> None:
#     """e.g.: hop config:get <app> FOO."""
#     env = app.get_runtime_env()
#     if setting in env:
#         log(f"{env[setting]}", fg="white")


@command
class ConfigGetCmd(Cmd):
    """e.g.: hop config:get <app> FOO."""

    name = "config:get"

    def add_arguments(self, parser) -> None:
        parser.add_argument("app", type=str)
        parser.add_argument("setting", type=str)

    def run(self, app: App, setting: str) -> None:
        env = app.get_runtime_env()
        if setting in env:
            log(f"{env[setting]}", fg="white")


# @hop3.command("config:set")
# @argument("app", type=AppParamType())
# @argument("settings", nargs=-1)
# def cmd_config_set(app: App, settings) -> None:
#     """e.g.: hop config:set <app> FOO=bar BAZ=quux."""
#     env = app.get_runtime_env()
#
#     for s in settings:
#         key, value = _parse_setting(s)
#         log(f"Setting {key:s}={value} for '{app.name:s}'", fg="white")
#         env[key] = value
#
#     config_file = app.virtualenv_path / "ENV"
#     write_settings(config_file, env)
#     do_deploy(app)


@command
class ConfigSetCmd(Cmd):
    """e.g.: hop config:set <app> FOO=bar BAZ=quux."""

    name = "config:set"

    def add_arguments(self, parser) -> None:
        parser.add_argument("app", type=str)
        parser.add_argument("settings", nargs="+")

    def run(self, app: App, settings: list[str]) -> None:
        env = app.get_runtime_env()

        for s in settings:
            key, value = self._parse_setting(s)
            log(f"Setting {key:s}={value} for '{app.name:s}'", fg="white")
            env[key] = value

        config_file = app.virtualenv_path / "ENV"
        write_settings(config_file, env)
        do_deploy(app)

    def _parse_setting(self, setting: str) -> tuple[str, str]:
        if "=" not in setting:
            msg = f"Error: malformed setting '{setting}'"
            raise Abort(msg)

        key, value = setting.split("=", 1)
        key = key.strip()
        value = value.strip()
        return key, value


# @hop3.command("config:unset")
# @argument("app", type=AppParamType())
# @argument("settings", nargs=-1)
# def cmd_config_unset(app: App, settings) -> None:
#     """e.g.: hop config:unset <app> FOO."""
#     env = app.get_runtime_env()
#
#     for s in settings:
#         if s in env:
#             del env[s]
#             log(f"Unsetting {s} for '{app.name}'")
#
#     config_file = app.virtualenv_path / "ENV"
#     write_settings(config_file, env)
#     do_deploy(app)


@command
class ConfigUnsetCmd(Cmd):
    """e.g.: hop config:unset <app> FOO."""

    name = "config:unset"

    def add_arguments(self, parser) -> None:
        parser.add_argument("app", type=str)
        parser.add_argument("settings", nargs="+")

    def run(self, app: App, settings: list[str]) -> None:
        env = app.get_runtime_env()

        for s in settings:
            if s in env:
                del env[s]
                log(f"Unsetting {s} for '{app.name}'")

        config_file = app.virtualenv_path / "ENV"
        write_settings(config_file, env)
        do_deploy(app)


# @hop3.command("config:live")
# @argument("app", type=AppParamType())
# def cmd_config_live(app: App) -> None:
#     """e.g.: hop config:live <app>."""
#     env = app.get_runtime_env()
#
#     if not env:
#         log(f"Warning: app '{app.name}' not deployed, no config found.", fg="yellow")
#         return
#
#     for k, v in sorted(env.items()):
#         log(f"{k}={v}", fg="white")


@command
class ConfigLiveCmd(Cmd):
    """e.g.: hop config:live <app>."""

    name = "config:live"

    def add_arguments(self, parser) -> None:
        parser.add_argument("app", type=str)

    def run(self, app: App) -> None:
        env = app.get_runtime_env()

        if not env:
            log(
                f"Warning: app '{app.name}' not deployed, no config found.", fg="yellow"
            )
            return

        for k, v in sorted(env.items()):
            log(f"{k}={v}", fg="white")
