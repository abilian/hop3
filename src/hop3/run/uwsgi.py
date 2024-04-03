from __future__ import annotations

import grp
import os
import pwd
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from click import secho as echo

from hop3.system.constants import (
    APP_ROOT,
    ENV_ROOT,
    LOG_ROOT,
    NGINX_ROOT,
    UWSGI_AVAILABLE,
    UWSGI_ENABLED,
    UWSGI_LOG_MAXSIZE,
)
from hop3.util.settings import parse_settings

__all__ = ["spawn_uwsgi_worker"]


def spawn_uwsgi_worker(app, kind, command, env, ordinal=1) -> None:
    """Set up and deploy a single worker of a given kind"""

    name = f"{app:s}_{kind:s}.{ordinal:d}.ini"
    env["PROC_TYPE"] = kind
    env_path = Path(ENV_ROOT, app)
    available = Path(UWSGI_AVAILABLE, name)
    enabled = Path(UWSGI_ENABLED, name)
    log_file = Path(LOG_ROOT, app, kind)

    settings = Settings()

    settings += [
        ("chdir", Path(APP_ROOT, app)),
        ("uid", pwd.getpwuid(os.getuid()).pw_name),
        ("gid", grp.getgrgid(os.getgid()).gr_name),
        ("master", "true"),
        ("project", app),
        ("max-requests", env.get("UWSGI_MAX_REQUESTS", "1024")),
        ("listen", env.get("UWSGI_LISTEN", "16")),
        ("processes", env.get("UWSGI_PROCESSES", "1")),
        ("procname-prefix", f"{app:s}:{kind:s}:"),
        ("enable-threads", env.get("UWSGI_ENABLE_THREADS", "true").lower()),
        ("log-x-forwarded-for", env.get("UWSGI_LOG_X_FORWARDED_FOR", "false").lower()),
        ("log-maxsize", env.get("UWSGI_LOG_MAXSIZE", UWSGI_LOG_MAXSIZE)),
        (
            "logfile-chown",
            f"{pwd.getpwuid(os.getuid()).pw_name}:{grp.getgrgid(os.getgid()).gr_name}",
        ),
        ("logfile-chmod", "640"),
        ("logto2", f"{log_file}.{ordinal:d}.log"),
        ("log-backupname", f"{log_file}.{ordinal:d}.log.old"),
    ]

    # only add virtualenv to uwsgi if it's a real virtualenv
    if Path(env_path, "bin", "activate_this.py").exists():
        settings.add("virtualenv", env_path)

    if "UWSGI_IDLE" in env:
        try:
            idle_timeout = int(env["UWSGI_IDLE"])
            settings += [
                ("idle", str(idle_timeout)),
                ("cheap", "True"),
                ("die-on-idle", "True"),
            ]
            echo(
                f"-----> uwsgi will start workers on demand and kill them after {idle_timeout}s of inactivity",
                fg="yellow",
            )
        except Exception:
            echo("Error: malformed setting 'UWSGI_IDLE', ignoring it.", fg="red")

    match kind:
        case "cron":
            cron_cmd = command.replace("*/", "-").replace("*", "-1")
            settings.add("cron", cron_cmd)

        case "jwsgi":
            settings += [
                ("module", command),
                ("threads", env.get("UWSGI_THREADS", "4")),
                ("plugin", "jvm"),
                ("plugin", "jwsgi"),
            ]

        case "rwsgi":
            settings += [
                ("module", command),
                ("threads", env.get("UWSGI_THREADS", "4")),
                ("plugin", "rack"),
                ("plugin", "rbrequire"),
                ("plugin", "post-buffering"),
            ]

        case "wsgi":
            settings += [
                ("module", command),
                ("threads", env.get("UWSGI_THREADS", "4")),
                ("plugin", "python3"),
            ]

            if "UWSGI_ASYNCIO" in env:
                try:
                    tasks = int(env["UWSGI_ASYNCIO"])
                    settings += [
                        ("plugin", "asyncio_python3"),
                        ("async", tasks),
                    ]
                    echo(
                        f"-----> uwsgi will support {tasks} async tasks",
                        fg="yellow",
                    )
                except ValueError:
                    echo(
                        "Error: malformed setting 'UWSGI_ASYNCIO', ignoring it.",
                        fg="red",
                    )

            # If running under nginx, don't expose a port at all
            if "NGINX_SERVER_NAME" in env:
                sock = Path(NGINX_ROOT, f"{app}.sock")
                echo(f"-----> nginx will talk to uWSGI via {sock}", fg="yellow")
                settings += [
                    ("socket", sock),
                    ("chmod-socket", "664"),
                ]
            else:
                echo(
                    "-----> nginx will talk to uWSGI via {BIND_ADDRESS:s}:{PORT:s}".format(
                        **env
                    ),
                    fg="yellow",
                )
                settings += [
                    ("http", "{BIND_ADDRESS:s}:{PORT:s}".format(**env)),
                    ("http-use-socket", "{BIND_ADDRESS:s}:{PORT:s}".format(**env)),
                    ("http-socket", "{BIND_ADDRESS:s}:{PORT:s}".format(**env)),
                ]
        case "web":
            echo(
                "-----> nginx will talk to the 'web' process via {BIND_ADDRESS:s}:{PORT:s}".format(
                    **env
                ),
                fg="yellow",
            )
            settings.add("attach-daemon", command)
        case "static":
            echo("-----> nginx serving static files only".format(**env), fg="yellow")
        case "cron":
            echo(f"-----> uwsgi scheduled cron for {command}", fg="yellow")
        case _:
            settings.add("attach-daemon", command)

    if kind in ["wsgi", "web"]:
        settings.add(
            "log-format",
            '%%(addr) - %%(user) [%%(ltime)] "%%(method) %%(uri) %%(proto)" %%(status) %%(size) "%%(referer)" "%%(uagent)" %%(msecs)ms',
        )

    # remove unnecessary variables from the env in nginx.ini
    for k in ["NGINX_ACL"]:
        if k in env:
            del env[k]

    # insert user defined uwsgi settings if set
    if include_file := env.get("UWSGI_INCLUDE_FILE"):
        settings += parse_settings(Path(APP_ROOT, app, include_file)).items()

    for k, v in env.items():
        settings.add("env", f"{k:s}={v}")

    if kind != "static":
        settings.write(Path(available))
        shutil.copyfile(available, enabled)


@dataclass(frozen=True)
class Settings:
    values: list[tuple[str, str]] = field(default_factory=list)

    def add(self, key, value) -> None:
        self.values.append((key, str(value)))

    def append(self, item) -> None:
        self.add(item[0], item[1])

    def extend(self, items) -> None:
        for item in items:
            self.append(item)

    def __iadd__(self, items) -> Settings:
        self.extend(items)
        return self

    def write(self, path: Path):
        with open(path, "w") as h:
            h.write("[uwsgi]\n")
            for k, v in self.values:
                h.write(f"{k:s} = {v}\n")
        return path
