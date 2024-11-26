# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands to manage apps lifecycle."""

from __future__ import annotations

import subprocess
from argparse import ArgumentParser

from hop3.core.app import App, list_apps
from hop3.deploy import do_deploy
from hop3.project.procfile import parse_procfile
from hop3.util import Abort, echo, multi_tail
from hop3.util.console import console

from ._base import Cmd, command


@command
class AppsCmd(Cmd):
    """List apps, e.g.: hop-agent apps."""

    def run(self):
        apps = list_apps()
        if not apps:
            echo("There are no applications deployed.")
            return

        for app in apps:
            if app.is_running:
                echo(f"* {app.name}", fg="green")
            else:
                echo(f"  {app.name}", fg="white")


@command
class DeployCmd(Cmd):
    """e.g.: hop-agent deploy <app>."""

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("app", type=str)

    def run(self, app: App) -> None:
        app.deploy()


@command
class DestroyCmd(Cmd):
    """e.g.: hop-agent destroy <app>."""

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("app", type=str)

    def run(self, app: App) -> None:
        app.destroy()


@command
class LogsCmd(Cmd):
    """Tail running logs, e.g: hop-agent logs <app> [<process>]."""

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("app", type=str)
        parser.add_argument("process", nargs=1, default="*")

    def run(self, app: App, process: str) -> None:
        logfiles = list(app.log_path.glob(process + ".*.log"))
        if len(logfiles) > 0:
            for line in multi_tail(logfiles):
                echo(line.strip(), fg="white")
        else:
            echo(f"No logs found for app '{app.name}'.", fg="yellow")


@command
class PsCmd(Cmd):
    """Show process count, e.g: hop-agent ps <app>."""

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("app", type=str)

    def run(self, app: App) -> None:
        scaling_file = app.virtualenv_path / "SCALING"

        if scaling_file.exists():
            echo(scaling_file.read_text().strip(), fg="white")
        else:
            echo(f"Error: no workers found for app '{app.name}'.", fg="red")


# @hop3.command("ps:scale")
# @argument("app", type=AppParamType())
# @argument("settings", nargs=-1)
# def cmd_ps_scale(app: App, settings: list[str]) -> None:
#     """e.g.: hop-agent ps:scale <app> <proc>=<count>."""
#     scaling_file = app.virtualenv_path / "SCALING"
#     worker_count = {k: int(v) for k, v in parse_procfile(scaling_file).items()}
#     deltas: dict[str, int] = {}
#     for s in settings:
#         try:
#             key, value = s.split("=", 1)
#             key = key.strip()
#             count = int(value.strip())  # check for integer value
#         except Exception:
#             msg = f"Error: malformed setting '{s}'"
#             raise Abort(msg)
#
#         if count < 0:
#             msg = f"Error: cannot scale type '{key}' below 0"
#             raise Abort(msg)
#         if key not in worker_count:
#             msg = f"Error: worker type '{key}' not present in '{app}'"
#             raise Abort(msg)
#         deltas[key] = count - worker_count[key]
#
#     do_deploy(app, deltas=deltas)


@command
class PsScaleCmd(Cmd):
    """e.g.: hop-agent ps:scale <app> <proc>=<count>."""

    name = "ps:scale"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("app", type=str)
        parser.add_argument("settings", nargs="+")

    def run(self, app: App, settings: list[str]) -> None:
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


# @hop3.command("run")
# @argument("app", type=AppParamType())
# @argument("cmd", nargs=-1)
# def cmd_run(app: App, cmd: list[str]) -> None:
#     """e.g.: hop-agent run <app> ls -- -al."""
#
#     # TODO: Need to make the file descriptors non-blocking and deal
#     # with it.
#     p = subprocess.Popen(
#         cmd,
#         stdin=subprocess.PIPE,
#         stdout=subprocess.PIPE,
#         stderr=subprocess.PIPE,
#         env=app.get_runtime_env(),
#         cwd=str(app.app_path),
#     )
#     # TODO: deal with stdin
#     out, err = p.communicate(b"")
#
#     console.echo(out.decode())
#     console.echo(err.decode())
#     # sys.stdout.write(out.decode())
#     # sys.stderr.write(err.decode())


@command
class RunCmd(Cmd):
    """e.g.: hop-agent run <app> ls -- -al."""

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("app", type=str)
        parser.add_argument("cmd", nargs="+")

    def run(self, app: App, cmd: list[str]) -> None:
        # TODO: Need to make the file descriptors non-blocking and deal
        # with it.
        p = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=app.get_runtime_env(),
            cwd=str(app.app_path),
        )
        # TODO: deal with stdin
        out, err = p.communicate(b"")

        console.echo(out.decode())
        console.echo(err.decode())
        # sys.stdout.write(out.decode())
        # sys.stderr.write(err.decode())


# @hop3.command("start")
# @argument("app", type=AppParamType())
# def cmd_start(app: App) -> None:
#     """Stop an app, e.g: hop-agent stop <app>."""
#     app.start()


@command
class StartCmd(Cmd):
    """Stop an app, e.g: hop-agent stop <app>."""

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("app", type=str)

    def run(self, app: App) -> None:
        app.start()


# @hop3.command("stop")
# @argument("app", type=AppParamType())
# def cmd_stop(app: App) -> None:
#     """Stop an app, e.g: hop-agent stop <app>."""
#     app.stop()


@command
class StopCmd(Cmd):
    """Stop an app, e.g: hop-agent stop <app>."""

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("app", type=str)

    def run(self, app: App) -> None:
        app.stop()


# @hop3.command("restart")
# @argument("app", type=AppParamType())
# def cmd_restart(app: App) -> None:
#     """Restart an app: hop-agent restart <app>."""
#     app.restart()


@command
class RestartCmd(Cmd):
    """Restart an app: hop-agent restart <app>."""

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("app", type=str)

    def run(self, app: App) -> None:
        app.restart()
