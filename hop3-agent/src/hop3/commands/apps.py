# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

"""CLI commands."""

from __future__ import annotations

import fcntl
import os
import subprocess
import sys
from glob import glob

from click import argument
from click import secho as echo

from hop3.core.app import get_app, list_apps
from hop3.deploy import do_deploy
from hop3.project.procfile import parse_procfile
from hop3.system.constants import LOG_ROOT
from hop3.util import exit_if_invalid, multi_tail
from hop3.util.console import Abort

from .cli import hop3


@hop3.command("apps")
def cmd_apps() -> None:
    """List apps, e.g.: hop-agent apps."""
    apps = list_apps()
    if not apps:
        echo("There are no applications deployed.")
        return

    for app in apps:
        if app.is_running:
            echo(f"* {app.name}", fg="green")
        else:
            echo(f"  {app.name}", fg="white")


@hop3.command("deploy")
@argument("app")
def cmd_deploy(app) -> None:
    """e.g.: hop-agent deploy <app>."""
    app_obj = get_app(app)
    app_obj.deploy()


@hop3.command("destroy")
@argument("app")
def cmd_destroy(app) -> None:
    """e.g.: hop-agent destroy <app>."""
    app_obj = get_app(app)
    app_obj.destroy()


@hop3.command("logs")
@argument("app")
@argument("process", nargs=1, default="*")
def cmd_logs(app, process) -> None:
    """Tail running logs, e.g: hop-agent logs <app> [<process>]."""
    app = exit_if_invalid(app)

    logfiles = glob(os.path.join(LOG_ROOT, app, process + ".*.log"))
    if len(logfiles) > 0:
        for line in multi_tail(app, logfiles):
            echo(line.strip(), fg="white")
    else:
        echo(f"No logs found for app '{app}'.", fg="yellow")


@hop3.command("ps")
@argument("app")
def cmd_ps(app: str) -> None:
    """Show process count, e.g: hop-agent ps <app>."""
    app_obj = get_app(app)
    scaling_file = app_obj.virtualenv_path / "SCALING"

    if scaling_file.exists():
        echo(scaling_file.read_text().strip(), fg="white")
    else:
        echo(f"Error: no workers found for app '{app}'.", fg="red")


@hop3.command("ps:scale")
@argument("app")
@argument("settings", nargs=-1)
def cmd_ps_scale(app: str, settings: list[str]) -> None:
    """e.g.: hop-agent ps:scale <app> <proc>=<count>."""
    app_obj = get_app(app)

    scaling_file = app_obj.virtualenv_path / "SCALING"
    worker_count = {k: int(v) for k, v in parse_procfile(scaling_file).items()}
    deltas: dict[str, int] = {}
    for s in settings:
        try:
            key, value = s.split("=", 1)
            key = key.strip()
            count = int(value.strip())  # check for integer value
        except Exception:
            raise Abort(f"Error: malformed setting '{s}'")

        if count < 0:
            raise Abort(f"Error: cannot scale type '{key}' below 0")
        if key not in worker_count:
            raise Abort(
                f"Error: worker type '{key}' not present in '{app}'",
            )
        deltas[key] = count - worker_count[key]

    do_deploy(app, deltas)


@hop3.command("run")
@argument("app")
@argument("cmd", nargs=-1)
def cmd_run(app: str, cmd: list[str]) -> None:
    """e.g.: hop-agent run <app> ls -- -al."""
    app_obj = get_app(app)

    for fd in [sys.stdout, sys.stderr]:
        make_nonblocking(fd.fileno())

    p = subprocess.Popen(
        cmd,
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr,
        env=app_obj.get_runtime_env(),
        cwd=str(app_obj.app_path),
        shell=True,
    )
    p.communicate()


def make_nonblocking(fd):
    """Put the file descriptor *fd* into non-blocking mode if
    possible.
    """
    flags = fcntl.fcntl(fd, fcntl.F_GETFL, 0)
    if not bool(flags & os.O_NONBLOCK):
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)


@hop3.command("restart")
@argument("app")
def cmd_restart(app) -> None:
    """Restart an app: hop-agent restart <app>."""
    app_obj = get_app(app)
    app_obj.restart()


@hop3.command("stop")
@argument("app")
def cmd_stop(app) -> None:
    """Stop an app, e.g: hop-agent stop <app>."""
    app_obj = get_app(app)
    app_obj.stop()
