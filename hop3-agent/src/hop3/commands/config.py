# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

"""CLI commands."""

from __future__ import annotations

from pathlib import Path

from click import argument

from hop3.core.app import get_app
from hop3.deploy import do_deploy
from hop3.system.constants import ENV_ROOT
from hop3.util.console import Abort, log
from hop3.util.settings import write_settings

from .cli import hop3


@hop3.command("config")
@argument("app")
def cmd_config(app) -> None:
    """Show config, e.g.: hop config <app>."""
    app_obj = get_app(app)
    env = app_obj.get_runtime_env()

    for k, v in sorted(env.items()):
        log(f"{k}={v}", fg="white")


@hop3.command("config:get")
@argument("app")
@argument("setting")
def cmd_config_get(app, setting) -> None:
    """e.g.: hop config:get <app> FOO."""
    app_obj = get_app(app)
    env = app_obj.get_runtime_env()
    if setting in env:
        log(f"{env[setting]}", fg="white")


@hop3.command("config:set")
@argument("app")
@argument("settings", nargs=-1)
def cmd_config_set(app, settings) -> None:
    """e.g.: hop config:set <app> FOO=bar BAZ=quux."""
    app_obj = get_app(app)
    env = app_obj.get_runtime_env()

    for s in settings:
        try:
            key, value = s.split("=", 1)
            key = key.strip()
            value = value.strip()
            log(f"Setting {key:s}={value} for '{app:s}'", fg="white")
            env[key] = value
        except Exception:
            raise Abort(f"Error: malformed setting '{s}'")

    config_file = Path(ENV_ROOT, app, "ENV")
    write_settings(config_file, env)
    do_deploy(app)


@hop3.command("config:unset")
@argument("app")
@argument("settings", nargs=-1)
def cmd_config_unset(app, settings) -> None:
    """e.g.: hop config:unset <app> FOO."""
    app_obj = get_app(app)
    env = app_obj.get_runtime_env()

    for s in settings:
        if s in env:
            del env[s]
            log(f"Unsetting {s} for '{app}'")

    config_file = Path(ENV_ROOT, app, "ENV")
    write_settings(config_file, env)
    do_deploy(app)


@hop3.command("config:live")
@argument("app")
def cmd_config_live(app) -> None:
    """e.g.: hop config:live <app>."""
    app_obj = get_app(app)
    env = app_obj.get_runtime_env()

    if not env:
        log(f"Warning: app '{app}' not deployed, no config found.", fg="yellow")
        return

    for k, v in sorted(env.items()):
        log(f"{k}={v}", fg="white")
