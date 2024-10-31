# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands to manage apps lifecycle."""

from __future__ import annotations

import fcntl
import os
import subprocess
import sys

from click import argument

from hop3.core.app import App, list_apps
from hop3.deploy import do_deploy
from hop3.project.procfile import parse_procfile
from hop3.util import Abort, echo, multi_tail

from .cli import hop3
from .types import AppParamType


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
@argument("app", type=AppParamType())
def cmd_deploy(app: App) -> None:
    """e.g.: hop-agent deploy <app>."""
    app.deploy()


@hop3.command("destroy")
@argument("app", type=AppParamType())
def cmd_destroy(app: App) -> None:
    """e.g.: hop-agent destroy <app>."""
    app.destroy()


@hop3.command("logs")
@argument("app", type=AppParamType())
@argument("process", nargs=1, default="*")
def cmd_logs(app: App, process) -> None:
    """Tail running logs, e.g: hop-agent logs <app> [<process>]."""

    logfiles = list(app.log_path.glob(process + ".*.log"))
    if len(logfiles) > 0:
        for line in multi_tail(logfiles):
            echo(line.strip(), fg="white")
    else:
        echo(f"No logs found for app '{app.name}'.", fg="yellow")


@hop3.command("ps")
@argument("app", type=AppParamType())
def cmd_ps(app: App) -> None:
    """Show process count, e.g: hop-agent ps <app>."""
    scaling_file = app.virtualenv_path / "SCALING"

    if scaling_file.exists():
        echo(scaling_file.read_text().strip(), fg="white")
    else:
        echo(f"Error: no workers found for app '{app.name}'.", fg="red")


@hop3.command("ps:scale")
@argument("app", type=AppParamType())
@argument("settings", nargs=-1)
def cmd_ps_scale(app: App, settings: list[str]) -> None:
    """e.g.: hop-agent ps:scale <app> <proc>=<count>."""
    scaling_file = app.virtualenv_path / "SCALING"
    worker_count = {k: int(v) for k, v in parse_procfile(scaling_file).items()}
    deltas: dict[str, int] = {}
    for s in settings:
        try:
            key, value = s.split("=", 1)
            key = key.strip()
            count = int(value.strip())  # check for integer value
        except Exception:
            msg = f"Error: malformed setting '{s}'"
            raise Abort(msg)

        if count < 0:
            msg = f"Error: cannot scale type '{key}' below 0"
            raise Abort(msg)
        if key not in worker_count:
            msg = f"Error: worker type '{key}' not present in '{app}'"
            raise Abort(msg)
        deltas[key] = count - worker_count[key]

    do_deploy(app, deltas=deltas)


@hop3.command("run")
@argument("app", type=AppParamType())
@argument("cmd", nargs=-1)
def cmd_run(app: App, cmd: list[str]) -> None:
    """e.g.: hop-agent run <app> ls -- -al."""
    for fd in [sys.stdout, sys.stderr]:
        make_nonblocking(fd.fileno())

    p = subprocess.Popen(
        cmd,
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr,
        env=app.get_runtime_env(),
        cwd=str(app.app_path),
        shell=True,
    )
    p.communicate()


@hop3.command("restart")
@argument("app", type=AppParamType())
def cmd_restart(app: App) -> None:
    """Restart an app: hop-agent restart <app>."""
    app.restart()


@hop3.command("stop")
@argument("app", type=AppParamType())
def cmd_stop(app: App) -> None:
    """Stop an app, e.g: hop-agent stop <app>."""
    app.stop()


# Utils


def make_nonblocking(fd):
    """Put the file descriptor *fd* into non-blocking mode if
    possible.
    """
    flags = fcntl.fcntl(fd, fcntl.F_GETFL, 0)
    if not bool(flags & os.O_NONBLOCK):
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
