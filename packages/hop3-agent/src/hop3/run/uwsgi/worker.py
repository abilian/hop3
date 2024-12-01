# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import grp
import os
import pwd
import shutil
from abc import abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from hop3.config import c
from hop3.util import Abort, log
from hop3.util.settings import parse_settings

from .settings import UwsgiSettings

if TYPE_CHECKING:
    from hop3.core.env import Env

__all__ = ["spawn_uwsgi_worker"]


def spawn_uwsgi_worker(
    app_name: str,
    kind: str,
    command: str,
    env: Env,
    ordinal=1,
) -> None:
    """
    Set up and deploy a single worker of a given kind.

    Input:
        app_name (str): The name of the application for which the worker is being spawned.
        kind (str): The type of worker to spawn (e.g., "static", "cron", "jwsgi", etc.).
        command (str): The command to be executed by the worker.
        env (Env): The environment in which the worker will be spawned.
        ordinal (int): The ordinal number of the worker, default is 1.
    """

    # if kind == "web":
    #     spawn_uwsgi_worker_web(app_name, kind, command, env, ordinal)
    #     return

    worker: UwsgiWorker
    match kind:
        case "static":
            log("nginx serving static files only", level=2, fg="yellow")
            return
        case "cron":
            worker = CronWorker(app_name, command, env, ordinal)
            log(f"uwsgi scheduled cron for {command}", level=2, fg="yellow")
        case "jwsgi":
            worker = JwsgiWorker(app_name, command, env, ordinal)
        case "rwsgi":
            worker = RwsgiWorker(app_name, command, env, ordinal)
        case "wsgi":
            worker = WsgiWorker(app_name, command, env, ordinal)
        case "web":
            worker = WebWorker(app_name, command, env, ordinal)
        case _:
            worker = GenericWorker(app_name, command, env, ordinal, kind=kind)

    worker.spawn()


@dataclass
class UwsgiWorker:
    app_name: str
    command: str
    env: Env
    ordinal: int = 1
    kind: str = ""
    settings: UwsgiSettings = field(default_factory=UwsgiSettings)

    log_format = ""

    def spawn(self) -> None:
        """
        Execute a series of setup operations to initialize and configure settings
        for the environment.

        This orchestrates the process of creating base settings,
        updating those settings, modifying the environment, and finally
        writing the updated settings to the necessary locations.
        """

        self.create_base_settings()
        self.update_settings()
        self.update_env()
        self.write_settings()

    def create_base_settings(self) -> None:
        """
        Configures and updates base settings for an application using uWSGI.

        This sets up the environment and configuration settings required
        for running an application with uWSGI. It adds various settings like user
        and group IDs, process types, logging configurations, and other uWSGI
        parameters. It also checks for virtual environment existence and handles
        optional idle settings.
        """
        from hop3.core.app import App

        env = self.env.copy()

        app = App(self.app_name)
        app_name = self.app_name

        env["PROC_TYPE"] = self.kind
        env_path = app.virtualenv_path
        log_path = app.log_path
        log_file = log_path / self.kind

        # Retrieve username and group name from system user and group IDs
        pw_name = pwd.getpwuid(os.getuid()).pw_name
        gr_name = grp.getgrgid(os.getgid()).gr_name

        self.settings += [
            ("chdir", app.src_path),
            ("uid", pw_name),
            ("gid", gr_name),
            ("master", "true"),
            ("project", app_name),
            ("max-requests", env.get("UWSGI_MAX_REQUESTS", "1024")),
            ("listen", env.get("UWSGI_LISTEN", "16")),
            ("processes", env.get("UWSGI_PROCESSES", "1")),
            ("procname-prefix", f"{app_name:s}:{self.kind:s}:"),
            ("enable-threads", env.get("UWSGI_ENABLE_THREADS", "true").lower()),
            (
                "log-x-forwarded-for",
                env.get("UWSGI_LOG_X_FORWARDED_FOR", "false").lower(),
            ),
            ("log-maxsize", env.get("UWSGI_LOG_MAXSIZE", c.UWSGI_LOG_MAXSIZE)),
            ("logfile-chown", f"{pw_name}:{gr_name}"),
            ("logfile-chmod", "640"),
            ("logto2", f"{log_file}.{self.ordinal:d}.log"),
            ("log-backupname", f"{log_file}.{self.ordinal:d}.log.old"),
        ]

        if self.log_format:
            self.settings.add("log-format", self.log_format)

        # only add virtualenv to uwsgi if it's a real virtualenv
        if Path(env_path, "bin", "activate_this.py").exists():
            self.settings.add("virtualenv", env_path)

        if "UWSGI_IDLE" in env:
            try:
                idle_timeout = int(env["UWSGI_IDLE"])
                self.settings += [
                    ("idle", str(idle_timeout)),
                    ("cheap", "True"),
                    ("die-on-idle", "True"),
                ]
                self.log(
                    "uwsgi will start workers on demand and kill them after"
                    f" {idle_timeout}s of inactivity"
                )
            except Exception:
                msg = "Error: malformed setting 'UWSGI_IDLE', ignoring it."
                raise Abort(msg)

    @abstractmethod
    def update_settings(self) -> None:
        ...
        # raise NotImplementedError

    def update_env(self) -> None:
        """
        Update the environment settings for the application.

        This updates the environment settings by removing unnecessary variables
        and inserting user-defined UWSGI settings if specified.
        """
        from hop3.core.app import App

        app = App(self.app_name)

        # remove unnecessary variables from the env in nginx.ini
        env = self.env.copy()
        for k in ["NGINX_ACL"]:
            if k in env:
                del env[k]

        # insert user defined uwsgi settings if set
        if include_file := env.get("UWSGI_INCLUDE_FILE"):
            include_file_path = app.src_path / include_file
            self.settings += parse_settings(include_file_path).items()

        for k, v in env.items():
            self.settings.add("env", f"{k:s}={v}")

    def write_settings(self) -> None:
        """
        Write configuration settings to a file and enable them by copying to another directory.

        This generates a filename based on the application name, type, and an ordinal number,
        writes the settings to a file in the 'UWSGI_AVAILABLE' directory, and then copies this file
        to the 'UWSGI_ENABLED' directory to make the settings active.
        """
        name = f"{self.app_name:s}_{self.kind:s}.{self.ordinal:d}.ini"
        uwsgi_available_path = c.UWSGI_AVAILABLE / name
        uwsgi_enabled_path = c.UWSGI_ENABLED / name
        self.settings.write(uwsgi_available_path)
        shutil.copyfile(uwsgi_available_path, uwsgi_enabled_path)

    def log(self, message) -> None:
        """
        Logs a formatted message with a specified log level and color.

        Input:
            message (str): The message template to be formatted and logged.
        """
        message = message.format(**self.env)
        log(message, level=2, fg="yellow")


@dataclass
class CronWorker(UwsgiWorker):
    kind = "cron"

    def update_settings(self) -> None:
        cron_cmd = self.command.replace("*/", "-").replace("*", "-1")
        self.settings.add("cron", cron_cmd)


@dataclass
class JwsgiWorker(UwsgiWorker):
    kind = "jwsgi"

    def update_settings(self) -> None:
        self.settings += [
            ("module", self.command),
            ("threads", self.env.get("UWSGI_THREADS", "4")),
            ("plugin", "jvm"),
            ("plugin", "jwsgi"),
        ]


@dataclass
class RwsgiWorker(UwsgiWorker):
    kind = "rwsgi"

    def update_settings(self) -> None:
        self.settings += [
            ("module", self.command),
            ("threads", self.env.get("UWSGI_THREADS", "4")),
            ("plugin", "rack"),
            ("plugin", "rbrequire"),
            ("plugin", "post-buffering"),
        ]


@dataclass
class WsgiWorker(UwsgiWorker):
    kind = "wsgi"

    log_format = (
        '%%(addr) - %%(user) [%%(ltime)] "%%(method) %%(uri) %%(proto)" %%(status)'
        ' %%(size) "%%(referer)" "%%(uagent)" %%(msecs)ms'
    )

    def update_settings(self) -> None:
        self.settings += [
            ("module", self.command),
            ("threads", self.env.get("UWSGI_THREADS", "4")),
            ("plugin", "python3"),
        ]

        if "UWSGI_ASYNCIO" in self.env:
            try:
                tasks = int(self.env["UWSGI_ASYNCIO"])
                self.settings += [
                    ("plugin", "asyncio_python3"),
                    ("async", tasks),
                ]
                self.log(f"uwsgi will support {tasks} async tasks")
            except ValueError:
                msg = "Error: malformed setting 'UWSGI_ASYNCIO'."
                raise Abort(msg)

        # If running under nginx, don't expose a port at all
        if "NGINX_SERVER_NAME" in self.env:
            sock = c.NGINX_ROOT / f"{self.app_name}.sock"
            self.log(f"nginx will talk to uWSGI via {sock}")
            self.settings += [
                ("socket", sock),
                ("chmod-socket", "664"),
            ]
        else:
            self.log("nginx will talk to uWSGI via {BIND_ADDRESS:s}:{PORT:s}")
            self.settings += [
                ("http", "{BIND_ADDRESS:s}:{PORT:s}".format(**self.env)),
                ("http-use-socket", "{BIND_ADDRESS:s}:{PORT:s}".format(**self.env)),
                ("http-socket", "{BIND_ADDRESS:s}:{PORT:s}".format(**self.env)),
            ]


@dataclass
class WebWorker(UwsgiWorker):
    kind = "web"

    log_format = (
        '%%(addr) - %%(user) [%%(ltime)] "%%(method) %%(uri) %%(proto)"'
        ' %%(status) %%(size) "%%(referer)" "%%(uagent)" %%(msecs)ms'
    )

    def update_settings(self) -> None:
        """
        Update the settings by adding the command to the 'attach-daemon' section.

        This modifies the current settings to include the specified
        command associated with the key 'attach-daemon'.
        """
        self.settings.add("attach-daemon", self.command)


@dataclass
class GenericWorker(UwsgiWorker):
    kind: str = "generic"

    def update_settings(self) -> None:
        self.settings.add("attach-daemon", self.command)
