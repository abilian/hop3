# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import grp
import os
import pwd
import shlex
import shutil
from abc import abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from hop3 import config as c
from hop3.lib import Diagnosis, abort_with_diagnosis, log
from hop3.lib.settings import parse_settings
from hop3.run.uwsgi.naming import vassal_name

from .settings import UwsgiSettings

if TYPE_CHECKING:
    from hop3.core.env import Env

__all__ = ["spawn_uwsgi_worker"]


def spawn_uwsgi_worker(
    app_name: str,
    kind: str,
    command: str,
    env: Env,
    ordinal: int = 1,
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


def _quote_env_value(value: object) -> str:
    """
    An env value, safe to sit inside ``'...'`` inside ``sh -c "..."``.

    Two layers of quoting apply to every exported value, and the second one is
    easy to miss. The value is wrapped in single quotes, so an apostrophe has to
    be closed and reopened (``'\\''``) — but that whole ``export K='v'`` string
    is then embedded in the double-quoted argument of ``sh -c "…"``, and inside
    double quotes the shell still interprets ``$``, a backtick, a backslash and
    a double quote. Single quotes do not protect it there.

    Handling only the apostrophe silently corrupted any value containing those
    characters. A JSON-valued setting lost its quotes outright — paperless-ngx's
    ``PAPERLESS_PROXY_SSL_HEADER='["HTTP_X_FORWARDED_PROTO","https"]'`` reached
    Django as ``[HTTP_X_FORWARDED_PROTO,https]`` and crashed every worker on
    ``json.loads`` — and a generated password containing ``$`` would have been
    mangled into a credential nobody could reproduce.

    The command itself is deliberately NOT escaped this way: a start command is
    written to use ``$PORT``, and that expansion is the point.
    """
    text = str(value)
    for char in ("\\", "`", '"', "$"):
        text = text.replace(char, "\\" + char)
    return text.replace("'", "'\\''")


#: Shell operators that make a command more than one program. `exec` applies to
#: the first word, so everything after one of these is silently dropped.
_CHAINING_OPERATORS = frozenset({"&&", "||", ";", "|", "&"})


def _refuse_compound_command(command: str, app_name: str, kind: str) -> None:
    """
    Refuse a worker command that `exec` would truncate.

    A worker is wrapped as ``sh -c "… ; exec <command>"``, so a command built
    out of several programs loses everything after the first: `exec` replaces
    the shell with that program and the rest is never reached. Nothing said so
    — the app came up running only its first segment, or not at all.

    Refused rather than repaired, because the platform already has the right
    shape for "do this, then serve": ``[run].before-run``. An author who truly
    wants a shell can ask for one explicitly, as `bash -c '…'`, which is a
    single program taking a script as its argument and passes this check.
    """
    # `punctuation_chars` is what makes this see an operator that is glued to
    # the word before it: plain `shlex.split` yields "migrate;" as one token and
    # the chain goes unnoticed. Quoted operators stay inside their argument,
    # which is why `bash -c 'a && b'` — one program, taking a script — passes.
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        words = list(lexer)
    except ValueError:
        # Unbalanced quotes: we cannot prove it is compound, so we do not
        # block on a guess. The shell will report its own parse error.
        return
    found = _CHAINING_OPERATORS.intersection(words)
    if not found:
        return
    operator = next(iter(sorted(found)))
    abort_with_diagnosis(
        Diagnosis(
            component="uWSGI worker",
            action=f"start the '{kind}' worker for '{app_name}'",
            reason=(
                f"its command chains several programs with {operator!r}, and a "
                f"worker command must be a single program: it is run with "
                f"`exec`, which replaces the shell with the first program, so "
                f"everything after {operator!r} would never run"
            ),
            hint=(
                "Move the setup half to [run].before-run, which runs once "
                "before the worker starts. If you really want a shell, ask "
                "for one explicitly: bash -c '<the whole thing>'."
            ),
            troubleshooting=[f"the command was: {command}"],
        )
    )


@dataclass
class UwsgiWorker:
    app_name: str
    command: str
    env: Env
    ordinal: int = 1
    kind: str = ""
    settings: UwsgiSettings = field(default_factory=UwsgiSettings)

    log_format: str = ""

    def spawn(self) -> None:
        """
        Execute a series of setup operations to initialize and configure
        settings for the environment.

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
        for running an application with uWSGI. It adds various settings
        like user and group IDs, process types, logging configurations,
        and other uWSGI parameters. It also checks for virtual
        environment existence and handles optional idle settings.
        """
        from hop3.orm import (  # ruff:ignore[import-outside-top-level]
            App,
        )

        env = self.env.copy()

        app = App(name=self.app_name)
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
            # Note: "project" directive is not supported by all uWSGI versions
            # (e.g., RHEL 9's uWSGI rejects it in strict mode)
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

        # Only add virtualenv to uWSGI if it's a valid Python virtual environment.
        # Check for pyvenv.cfg (created by venv) or activate_this.py (created by virtualenv).
        is_venv = Path(env_path, "pyvenv.cfg").exists()
        is_virtualenv = Path(env_path, "bin", "activate_this.py").exists()
        if is_venv or is_virtualenv:
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
                abort_with_diagnosis(
                    Diagnosis(
                        component="uWSGI worker",
                        action="configure idle timeout",
                        reason=(
                            f"UWSGI_IDLE must be an integer (seconds), got "
                            f"{env['UWSGI_IDLE']!r}"
                        ),
                        hint=(
                            "Set UWSGI_IDLE to the number of seconds of "
                            "inactivity before workers are killed"
                        ),
                        troubleshooting=[
                            f"hop3 config set {self.app_name} UWSGI_IDLE=60",
                            f"hop3 config unset {self.app_name} UWSGI_IDLE",
                        ],
                    )
                )

    @abstractmethod
    def update_settings(self) -> None:
        ...
        # raise NotImplementedError

    def attach_daemon(self) -> None:
        """
        Run this worker's command as a uWSGI ``attach-daemon``.

        Commands are wrapped in 'sh -c' to enable shell variable expansion
        (e.g., $PORT) which is standard for Heroku-style Procfiles.

        Trust model
        -----------
        ``self.command`` and ``self.env`` are owned by the app's deployer:
        the user who pushed this app's Procfile/hop3.toml gets to pick
        the entrypoint and environment, and the app already runs *as*
        that deployer's app context. There is no privilege boundary
        between "the command they wrote" and "the shell that executes
        the command they wrote", so the f-string below does not cross
        a security boundary.

        The single-quote escaping on env values is a *correctness*
        measure (so a legitimate apostrophe in a value doesn't break
        the shell parse), not a security control. Do not "harden" this
        by, say, list-form ``subprocess`` — uWSGI's ``attach-daemon``
        only takes a shell string, and Procfile commands legitimately
        rely on ``$PORT`` expansion.

        What they may **not** rely on is chaining. The command is `exec`'d,
        so it has to be one program: in ``a && b``, `exec` lands on ``a``,
        the shell is replaced by it, and ``b`` never runs. This docstring
        used to promise ``&&`` chains worked, which is how the php-fpm
        runtime shipped with a ``sed … && exec php-fpm …`` worker that never
        started a pool. :func:`_refuse_compound_command` now says so instead
        of letting the tail be dropped in silence.
        """
        from hop3.orm import (  # ruff:ignore[import-outside-top-level]
            App,
        )

        app = App(name=self.app_name)

        # The PATH the spawner built comes FIRST. It already carries the build
        # artifact's `path_prepend` — for a Nix app that is where every binary
        # lives, since `virtualenv_path` holds nothing. Rebuilding PATH from a
        # virtualenv shape and discarding this made a bare worker command
        # ("bugsink-runsnappea") not found, while the web process survived
        # because its command is an absolute store path. The background worker
        # is the one that pays, and it pays by crash-looping until uWSGI
        # throttles it and the whole app is abandoned.
        path_dirs = [p for p in self.env.get("PATH", "").split(":") if p]

        # Virtualenv and node_modules bin directories, for the toolchains that
        # do install into the app's own tree.
        venv_bin = app.virtualenv_path / "bin"
        src_node_bin = app.src_path / "node_modules" / ".bin"
        venv_node_bin = app.virtualenv_path / "node_modules" / ".bin"

        path_dirs.append(str(venv_bin))
        if src_node_bin.exists():
            path_dirs.append(str(src_node_bin))
        if venv_node_bin.exists():
            path_dirs.append(str(venv_node_bin))

        path_dirs.extend([
            "/usr/local/sbin",
            "/usr/local/bin",
            "/usr/sbin",
            "/usr/bin",
        ])
        # Ordered dedup: the artifact's entries already appear above, and a
        # repeat would only make the exported PATH harder to read.
        path_value = ":".join(dict.fromkeys(path_dirs))

        # Build exports for ALL environment variables
        # uWSGI's attach-daemon spawns a subprocess that doesn't inherit
        # env vars from the uWSGI config, so we must export them explicitly
        exports = [f"export PATH={path_value}"]
        for key, value in self.env.items():
            # PATH is folded into path_value above; NGINX_ACL is not the app's.
            if key in {"NGINX_ACL", "PATH"}:
                continue
            exports.append(f"export {key}='{_quote_env_value(value)}'")

        # Wrap command in shell with all exports and explicit cd to src/
        # Note: uWSGI's chdir directive may not apply to attach-daemon processes,
        # so we explicitly cd to the source directory.
        #
        # Redirect stdout AND stderr to the app log file so application
        # output (PHP exceptions, Python tracebacks, Node startup errors,
        # …) is captured and visible via `hop3 app logs`. Node apps in
        # particular often write critical startup errors to stdout (e.g.
        # HedgeDoc 1.10 config-validation failures), so `2>>` alone loses
        # them; `>>file 2>&1` captures both.
        log_path = app.log_path
        daemon_log = f"{log_path}/{self.kind}.{self.ordinal}.log"
        exports_str = "; ".join(exports)
        _refuse_compound_command(self.command, app.name, self.kind)
        shell_cmd = f'sh -c "cd {app.src_path} && {exports_str}; exec {self.command} >>{daemon_log} 2>&1"'
        self.settings.add("attach-daemon", shell_cmd)

    def update_env(self) -> None:
        """
        Update the environment settings for the application.

        This updates the environment settings by removing unnecessary
        variables and inserting user-defined UWSGI settings if
        specified.
        """
        from hop3.orm import (  # ruff:ignore[import-outside-top-level]
            App,
        )

        app = App(name=self.app_name)

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
        Write configuration settings to a file and enable them by copying to
        another directory.

        This generates a filename based on the application name, type,
        and an ordinal number, writes the settings to a file in the
        'UWSGI_AVAILABLE' directory, and then copies this file to the
        'UWSGI_ENABLED' directory to make the settings active.
        """
        name = vassal_name(self.app_name, self.kind, self.ordinal)
        uwsgi_available_path = c.UWSGI_AVAILABLE / name
        uwsgi_enabled_path = c.UWSGI_ENABLED / name
        self.settings.write(uwsgi_available_path)
        shutil.copyfile(uwsgi_available_path, uwsgi_enabled_path)

    def log(self, message: str) -> None:
        """
        Logs a formatted message with a specified log level and color.

        Input:
            message (str): The message template to be formatted and logged.
        """
        message = message.format(**self.env)
        log(message, level=2, fg="yellow")


@dataclass
class CronWorker(UwsgiWorker):
    kind: str = "cron"

    def update_settings(self) -> None:
        cron_cmd = self.command.replace("*/", "-").replace("*", "-1")
        self.settings.add("cron", cron_cmd)


@dataclass
class JwsgiWorker(UwsgiWorker):
    kind: str = "jwsgi"

    def update_settings(self) -> None:
        self.settings += [
            ("module", self.command),
            ("threads", self.env.get("UWSGI_THREADS", "4")),
            ("plugin", "jvm"),
            ("plugin", "jwsgi"),
        ]


@dataclass
class RwsgiWorker(UwsgiWorker):
    kind: str = "rwsgi"

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
    kind: str = "wsgi"

    log_format: str = (
        '%%(addr) - %%(user) [%%(ltime)] "%%(method) %%(uri) %%(proto)" %%(status)'
        ' %%(size) "%%(referer)" "%%(uagent)" %%(msecs)ms'
    )

    def update_settings(self) -> None:
        from hop3.orm import (  # ruff:ignore[import-outside-top-level]
            App,
        )

        app = App(name=self.app_name)

        self.settings += [
            ("module", self.command),
            ("threads", self.env.get("UWSGI_THREADS", "4")),
            # Strict mode catches config errors early
            ("need-app", "true"),
            ("strict", "true"),
            ("catch-exceptions", "true"),
            ("pythonpath", str(app.src_path)),
        ]

        # Note: No plugin directive needed - uWSGI is installed via pip
        # with Python support built-in (not system-packaged with plugins)

        if "UWSGI_ASYNCIO" in self.env:
            try:
                tasks = int(self.env["UWSGI_ASYNCIO"])
                self.settings += [
                    ("async", tasks),
                ]
                self.log(f"uwsgi will support {tasks} async tasks")
            except ValueError:
                abort_with_diagnosis(
                    Diagnosis(
                        component="uWSGI worker",
                        action="configure asyncio tasks",
                        reason=(
                            f"UWSGI_ASYNCIO must be an integer (number of "
                            f"async tasks), got {self.env['UWSGI_ASYNCIO']!r}"
                        ),
                        hint=(
                            "Set UWSGI_ASYNCIO to the desired number of "
                            "concurrent async tasks, e.g. 100"
                        ),
                        troubleshooting=[
                            f"hop3 config set {self.app_name} UWSGI_ASYNCIO=100",
                            f"hop3 config unset {self.app_name} UWSGI_ASYNCIO",
                        ],
                    )
                )

        # Always use HTTP socket for direct access and nginx proxying
        # This simplifies local development and testing
        bind_addr = self.env.get("BIND_ADDRESS", "127.0.0.1")
        port = self.env.get("PORT", "5000")
        self.log(f"uWSGI will listen on http://{bind_addr}:{port}")
        self.settings += [
            ("http-socket", f"{bind_addr}:{port}"),
        ]


@dataclass
class WebWorker(UwsgiWorker):
    kind: str = "web"

    log_format: str = (
        '%%(addr) - %%(user) [%%(ltime)] "%%(method) %%(uri) %%(proto)"'
        ' %%(status) %%(size) "%%(referer)" "%%(uagent)" %%(msecs)ms'
    )

    def update_settings(self) -> None:
        """Run this worker's command as a uWSGI ``attach-daemon``."""
        self.attach_daemon()


@dataclass
class GenericWorker(UwsgiWorker):
    kind: str = "generic"

    def update_settings(self) -> None:
        """Run this worker's command as a uWSGI ``attach-daemon``."""
        self.attach_daemon()
