"""
CLI commands
"""

from __future__ import annotations

import os
from pathlib import Path

from click import argument

from hop3.deploy import do_deploy
from hop3.system.constants import ENV_ROOT
from hop3.util import exit_if_invalid
from hop3.util.console import Abort, log
from hop3.util.settings import parse_settings, write_settings

from .cli import hop3


@hop3.command("config")
@argument("app")
def cmd_config(app) -> None:
    """Show config, e.g.: hop config <app>"""

    app = exit_if_invalid(app)

    config_file = os.path.join(ENV_ROOT, app, "ENV")
    if os.path.exists(config_file):
        log(open(config_file).read().strip(), fg="white")
    else:
        log(f"Warning: app '{app}' not deployed, no config found.", fg="yellow")


@hop3.command("config:get")
@argument("app")
@argument("setting")
def cmd_config_get(app, setting) -> None:
    """e.g.: hop config:get <app> FOO"""

    app = exit_if_invalid(app)

    config_file = os.path.join(ENV_ROOT, app, "ENV")
    if os.path.exists(config_file):
        env = parse_settings(config_file)
        if setting in env:
            log(f"{env[setting]}", fg="white")
    else:
        log(f"Warning: no active configuration for '{app}'")


@hop3.command("config:set")
@argument("app")
@argument("settings", nargs=-1)
def cmd_config_set(app, settings) -> None:
    """e.g.: hop config:set <app> FOO=bar BAZ=quux"""

    app = exit_if_invalid(app)

    config_file = Path(ENV_ROOT, app, "ENV")
    env = parse_settings(config_file)
    for s in settings:
        try:
            k, v = map(lambda x: x.strip(), s.split("=", 1))
            env[k] = v
            log(f"Setting {k:s}={v} for '{app:s}'", fg="white")
        except Exception:
            raise Abort(f"Error: malformed setting '{s}'")

    write_settings(config_file, env)
    do_deploy(app)


@hop3.command("config:unset")
@argument("app")
@argument("settings", nargs=-1)
def cmd_config_unset(app, settings) -> None:
    """e.g.: hop config:unset <app> FOO"""

    app = exit_if_invalid(app)

    config_file = os.path.join(ENV_ROOT, app, "ENV")
    env = parse_settings(config_file)
    for s in settings:
        if s in env:
            del env[s]
            log(f"Unsetting {s} for '{app}'")

    write_settings(config_file, env)
    do_deploy(app)


@hop3.command("config:live")
@argument("app")
def cmd_config_live(app) -> None:
    """e.g.: hop config:live <app>"""

    app = exit_if_invalid(app)

    live_env = Path(ENV_ROOT, app, "LIVE_ENV")
    if live_env.exists():
        lines = live_env.read_text().strip().split("\n")
        lines.sort()
        log("\n".join(lines), fg="white")
    else:
        log(f"Warning: app '{app}' not deployed, no config found.", fg="yellow")
