# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""CLI commands to manage apps lifecycle."""

from __future__ import annotations

import subprocess
from argparse import ArgumentParser
from typing import TYPE_CHECKING

from hop3.cli.registry import command
from hop3.deploy import do_deploy
from hop3.orm import AppRepository
from hop3.project.procfile import parse_procfile
from hop3.util import Abort, echo, multi_tail
from hop3.util.console import console

if TYPE_CHECKING:
    from hop3.orm import App


@command
class AppsCmd:
    """List apps (running or stopped)."""

    def run(self, db_session):
        app_repo = AppRepository(session=db_session)
        apps = app_repo.list()
        if not apps:
            echo("There are no applications deployed.")
            return

        for app in apps:
            if app.is_running:
                echo(f"* {app.name}", fg="green")
            else:
                echo(f"  {app.name}", fg="white")


@command
class DeployCmd:
    """Deploy app."""

    def run(self, app: App) -> None:
        app.deploy()


@command
class DestroyCmd:
    """Destroy app, remove all files."""

    def run(self, app: App, db_session) -> None:
        app.destroy()
        db_session.delete(app)


@command
class LogsCmd:
    """Tail running logs, e.g: hop-agent logs <app> [<process>]."""

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("process", type=str, default="*")

    def run(self, app: App, process: str) -> None:
        logfiles = list(app.log_path.glob(process + ".*.log"))
        if len(logfiles) > 0:
            for line in multi_tail(logfiles):
                echo(line.strip(), fg="white")
        else:
            echo(f"No logs found for app '{app.name}'.", fg="yellow")


@command
class PsCmd:
    """Show process count for app."""

    def run(self, app: App) -> None:
        scaling_file = app.virtualenv_path / "SCALING"

        if scaling_file.exists():
            echo(scaling_file.read_text().strip(), fg="white")
        else:
            echo(f"Error: no workers found for app '{app.name}'.", fg="red")


@command
class PsScaleCmd:
    """Set the process count: `hop ps:scale <proc>=<count>`."""

    name = "ps:scale"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("settings", nargs="+")

    def run(self, app: App, settings: list[str]) -> None:
        scaling_file = app.virtualenv_path / "SCALING"
        worker_count = {k: int(v) for k, v in parse_procfile(scaling_file).items()}
        deltas: dict[str, int] = {}
        for s in settings:
            try:
                key, value = s.split("=", 1)
                key = key.strip()
                # check for integer value
                count = int(value.strip())
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


@command
class RunCmd:
    """Run command in the context of app, e.g.: hop run ls -- -al."""

    def add_arguments(self, parser: ArgumentParser) -> None:
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


@command
class StartCmd:
    """Stop an app."""

    def run(self, app: App) -> None:
        app.start()


@command
class StopCmd:
    """Stop an app."""

    def run(self, app: App) -> None:
        app.stop()


@command
class RestartCmd:
    """Restart an app."""

    def run(self, app: App) -> None:
        app.restart()
