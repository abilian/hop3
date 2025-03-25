# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands."""

from __future__ import annotations

from .base import Command

# from hop3.service import get_app



class ConfigCommand(Command):
    """Manage an application config / env."""

    name = "config"

    def subcommands(self) -> list[Command]:
        return [
            ShowSubcommand(),
            GetSubcommand(),
            LiveSubcommand(),
        ]


class ShowSubcommand(Command):
    """Show config, e.g.: hop config <app>."""

    name = "show"

    def call(self, app_name):
        app = get_app(app_name)
        env = app.get_env()

        rows = [[k, v] for k, v in env.items()]
        return [
            {
                "t": "table",
                "headers": ["Key", "Value"],
                "rows": rows,
            }
        ]


class GetSubcommand(Command):
    """e.g.: hop config:get <app> FOO."""

    name = "get"

    def call(self, app_name, setting):
        app = get_app(app_name)
        env = app.get_env()
        if setting in env:
            return [{"t": "text", "text": env[setting]}]
        else:
            return [{"t": "text", "text": f"Setting '{setting}' not found."}]


class LiveSubcommand(Command):
    """e.g.: hop config:live <app>."""

    name = "live"

    def call(self, app_name):
        app = get_app(app_name)
        env = app.get_runtime_env()

        if not env:
            return [
                {
                    "t": "text",
                    "text": f"Warning: app '{app_name}' not deployed, no config found.",
                }
            ]

        rows = [[k, v] for k, v in env.items()]
        return [
            {
                "t": "table",
                "headers": ["Key", "Value"],
                "rows": rows,
            }
        ]


# @hop3.command("config:live")
# @argument("app")
# def cmd_config_live(app) -> None:
#     """e.g.: hop config:live <app>."""
#     app_obj = get_app(app)
#     env = app_obj.get_runtime_env()
#
#     if not env:
#         log(f"Warning: app '{app}' not deployed, no config found.", fg="yellow")
#         return
#
#     for k, v in sorted(env.items()):
#         log(f"{k}={v}", fg="white")


# @hop3.command("config:set")
# @argument("app")
# @argument("settings", nargs=-1)
# def cmd_config_set(app, settings) -> None:
#     """e.g.: hop config:set <app> FOO=bar BAZ=quux."""
#     app_obj = get_app(app)
#     env = app_obj.get_runtime_env()
#
#     for s in settings:
#         try:
#             key, value = s.split("=", 1)
#             key = key.strip()
#             value = value.strip()
#             log(f"Setting {key:s}={value} for '{app:s}'", fg="white")
#             env[key] = value
#         except Exception:
#             raise Abort(f"Error: malformed setting '{s}'")
#
#     config_file = Path(ENV_ROOT, app, "ENV")
#     write_settings(config_file, env)
#     do_deploy(app)
#
#
# @hop3.command("config:unset")
# @argument("app")
# @argument("settings", nargs=-1)
# def cmd_config_unset(app, settings) -> None:
#     """e.g.: hop config:unset <app> FOO."""
#     app_obj = get_app(app)
#     env = app_obj.get_runtime_env()
#
#     for s in settings:
#         if s in env:
#             del env[s]
#             log(f"Unsetting {s} for '{app}'")
#
#     config_file = Path(ENV_ROOT, app, "ENV")
#     write_settings(config_file, env)
#     do_deploy(app)
#
#
# @hop3.command("config:live")
# @argument("app")
# def cmd_config_live(app) -> None:
#     """e.g.: hop config:live <app>."""
#     app_obj = get_app(app)
#     env = app_obj.get_runtime_env()
#
#     if not env:
#         log(f"Warning: app '{app}' not deployed, no config found.", fg="yellow")
#         return
#
#     for k, v in sorted(env.items()):
#         log(f"{k}={v}", fg="white")
