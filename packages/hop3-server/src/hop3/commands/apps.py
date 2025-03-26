# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from hop3.lib import echo
from hop3.lib.registry import register
from hop3.orm import App, AppRepository

from ._base import Command

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@register
@dataclass(frozen=True)
class Apps(Command):
    """List apps (running or stopped)."""

    db_session: Session

    name = "apps"

    def call(self, *args):
        app_repo = AppRepository(session=self.db_session)
        apps = app_repo.list()
        if not apps:
            echo("There are no applications deployed.")
            return []

        for app in apps:
            if app.is_running:
                echo(f"* {app.name}", fg="green")
            else:
                echo(f"  {app.name}", fg="white")

        rows = [[app.name, app.status, app.worker_count] for app in apps]
        return [
            {
                "t": "table",
                "headers": ["Name", "Status", "Workers"],
                "rows": rows,
            }
        ]


@register
@dataclass(frozen=True)
class Logs(Command):
    """Show application logs."""

    db_session: Session

    name = "logs"

    def call(self, *args):
        app_name = args[0]
        app_repo = AppRepository(session=self.db_session)
        app = app_repo.get(App.name == app_name)
        # TODO: by process
        logs = app.get_logs()
        return [
            {
                "t": "text",
                "text": "\n".join(logs),
            }
        ]


# # def cmd_deploy(app) -> None:
# #     """e.g.: hop deploy <app>."""
# #     app_obj = get_app(app)
# #     app_obj.deploy()
# #
# #
# # def cmd_destroy(app) -> None:
# #     """e.g.: hop destroy <app>."""
# #     app_obj = get_app(app)
# #     app_obj.destroy()
# #
# #
# # def cmd_ps(app: str) -> None:
# #     """Show process count, e.g: hop ps <app>."""
# #     app_obj = get_app(app)
# #     scaling_file = app_obj.virtualenv_path / "SCALING"
# #
# #     if scaling_file.exists():
# #         echo(scaling_file.read_text().strip(), fg="white")
# #     else:
# #         echo(f"Error: no workers found for app '{app}'.", fg="red")
# #
# #
# # def cmd_ps_scale(app: str, settings: list[str]) -> None:
# #     """e.g.: hop ps:scale <app> <proc>=<count>."""
# #     app_obj = get_app(app)
# #
# #     scaling_file = app_obj.virtualenv_path / "SCALING"
# #     worker_count = {k: int(v) for k, v in parse_procfile(scaling_file).items()}
# #     deltas: dict[str, int] = {}
# #     for s in settings:
# #         try:
# #             key, value = s.split("=", 1)
# #             key = key.strip()
# #             count = int(value.strip())  # check for integer value
# #         except Exception:
# #             raise ValueError(f"Error: malformed setting '{s}'")
# #
# #         if count < 0:
# #             raise ValueError(f"Error: cannot scale type '{key}' below 0")
# #         if key not in worker_count:
# #             raise ValueError(
# #                 f"Error: worker type '{key}' not present in '{app}'",
# #             )
# #         deltas[key] = count - worker_count[key]
# #
# #     # TODO
# #     # do_deploy(app, deltas)
# #
# #
# # def cmd_run(app: str, cmd: list[str]) -> None:
# #     """e.g.: hop run <app> ls -- -al."""
# #     app_obj = get_app(app)
# #
# #     for fd in [sys.stdout, sys.stderr]:
# #         make_nonblocking(fd.fileno())
# #
# #     p = subprocess.Popen(
# #         cmd,
# #         stdin=sys.stdin,
# #         stdout=sys.stdout,
# #         stderr=sys.stderr,
# #         env=app_obj.get_runtime_env(),
# #         cwd=str(app_obj.app_path),
# #         shell=True,
# #     )
# #     p.communicate()
# #
# #
# # def make_nonblocking(fd):
# #     """Put the file descriptor *fd* into non-blocking mode if
# #     possible.
# #     """
# #     flags = fcntl.fcntl(fd, fcntl.F_GETFL, 0)
# #     if not bool(flags & os.O_NONBLOCK):
# #         fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
# #
# #
# # def cmd_restart(app) -> None:
# #     """Restart an app: hop-agent restart <app>."""
# #     app_obj = get_app(app)
# #     app_obj.restart()
# #
# #
# # def cmd_stop(app) -> None:
# #     """Stop an app, e.g: hop-agent stop <app>."""
# #     app_obj = get_app(app)
# #     app_obj.stop()
