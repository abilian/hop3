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

from hop3.system.constants import (
    APP_ROOT,
    ENV_ROOT,
    LOG_ROOT,
    NGINX_ROOT,
    UWSGI_AVAILABLE,
    UWSGI_ENABLED,
    UWSGI_LOG_MAXSIZE,
)
from hop3.util import Abort, echo, log
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
    """Set up and deploy a single worker of a given kind."""

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
        self.create_base_settings()
        self.update_settings()
        self.update_env()
        self.write_settings()

    def create_base_settings(self) -> None:
        env = self.env.copy()

        app_name = self.app_name

        env["PROC_TYPE"] = self.kind
        env_path = ENV_ROOT / app_name
        log_file = LOG_ROOT / app_name / self.kind

        pw_name = pwd.getpwuid(os.getuid()).pw_name
        gr_name = grp.getgrgid(os.getgid()).gr_name

        self.settings += [
            ("chdir", APP_ROOT / app_name),
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
            ("log-maxsize", env.get("UWSGI_LOG_MAXSIZE", UWSGI_LOG_MAXSIZE)),
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
        # remove unnecessary variables from the env in nginx.ini
        env = self.env.copy()
        for k in ["NGINX_ACL"]:
            if k in env:
                del env[k]

        # insert user defined uwsgi settings if set
        if include_file := env.get("UWSGI_INCLUDE_FILE"):
            self.settings += parse_settings(
                Path(APP_ROOT, self.app_name, include_file)
            ).items()

        for k, v in env.items():
            self.settings.add("env", f"{k:s}={v}")

    def write_settings(self) -> None:
        name = f"{self.app_name:s}_{self.kind:s}.{self.ordinal:d}.ini"
        uwsgi_available_path = UWSGI_AVAILABLE / name
        uwsgi_enabled_path = UWSGI_ENABLED / name
        self.settings.write(uwsgi_available_path)
        shutil.copyfile(uwsgi_available_path, uwsgi_enabled_path)

    def log(self, message) -> None:
        message = message.format(**self.env)
        log(f"-----> {message}", fg="yellow")


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
                self.log(f"-----> uwsgi will support {tasks} async tasks")
            except ValueError:
                msg = "Error: malformed setting 'UWSGI_ASYNCIO'."
                raise Abort(msg)

        # If running under nginx, don't expose a port at all
        if "NGINX_SERVER_NAME" in self.env:
            sock = NGINX_ROOT / f"{self.app_name}.sock"
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
        tpl = (
            "-----> nginx will talk to the 'web' process via {BIND_ADDRESS:s}:{PORT:s}"
        )
        echo(
            tpl.format(**self.env),
            fg="yellow",
        )
        self.settings.add("attach-daemon", self.command)


@dataclass
class GenericWorker(UwsgiWorker):
    kind: str = "generic"

    def update_settings(self) -> None:
        self.settings.add("attach-daemon", self.command)
