# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import functools
import grp
import os
import pwd
import shutil
import subprocess
from abc import abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from hop3 import config as c
from hop3.lib import Abort, log
from hop3.lib.settings import parse_settings

from .settings import UwsgiSettings

if TYPE_CHECKING:
    from hop3.core.env import Env

__all__ = ["spawn_uwsgi_worker"]


@functools.cache
def _needs_python_plugin() -> bool:
    """Check if uWSGI needs the python3 plugin to be loaded explicitly.

    System-packaged uWSGI (apt/yum) uses modular plugins and needs this.
    Pip-installed uWSGI has Python built-in and doesn't need it.

    Returns:
        True if plugin directive is needed, False otherwise.
    """
    try:
        # Check if python3 plugin file exists (system uWSGI)
        # Different distros put it in different places
        plugin_paths = [
            # Debian/Ubuntu
            Path("/usr/lib/uwsgi/plugins/python3_plugin.so"),
            Path("/usr/lib/uwsgi/plugins/python312_plugin.so"),
            Path("/usr/lib/uwsgi/plugins/python311_plugin.so"),
            Path("/usr/lib/uwsgi/plugins/python310_plugin.so"),
            # Ubuntu with arch-specific paths
            Path("/usr/lib/x86_64-linux-gnu/uwsgi/plugins/python3_plugin.so"),
            Path("/usr/lib/aarch64-linux-gnu/uwsgi/plugins/python3_plugin.so"),
            # RHEL/Fedora
            Path("/usr/lib64/uwsgi/python3_plugin.so"),
        ]
        for path in plugin_paths:
            if path.exists():
                return True

        # Also check by globbing the plugin directory
        plugin_dirs = [
            Path("/usr/lib/uwsgi/plugins"),
            Path("/usr/lib64/uwsgi"),
        ]
        for plugin_dir in plugin_dirs:
            if plugin_dir.is_dir():
                # If there are any python*_plugin.so files, we need plugins
                if list(plugin_dir.glob("python*_plugin.so")):
                    return True

        # Alternative: check if uWSGI binary is in /usr/bin (system) vs venv
        result = subprocess.run(
            ["which", "uwsgi"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            uwsgi_path = result.stdout.strip()
            # System uWSGI is typically in /usr/bin
            if uwsgi_path.startswith("/usr/bin"):
                return True

        return False
    except Exception:
        # If detection fails, assume pip-installed (no plugin needed)
        return False


def spawn_uwsgi_worker(
    app_name: str,
    kind: str,
    command: str,
    env: Env,
    ordinal=1,
) -> None:
    """Set up and deploy a single worker of a given kind.

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

    log_format: str = ""

    def spawn(self) -> None:
        """Execute a series of setup operations to initialize and configure
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
        """Configures and updates base settings for an application using uWSGI.

        This sets up the environment and configuration settings required
        for running an application with uWSGI. It adds various settings
        like user and group IDs, process types, logging configurations,
        and other uWSGI parameters. It also checks for virtual
        environment existence and handles optional idle settings.
        """
        from hop3.orm import App  # noqa: PLC0415 - Avoid circular import

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
                msg = "Error: malformed setting 'UWSGI_IDLE', ignoring it."
                raise Abort(msg)

    @abstractmethod
    def update_settings(self) -> None:
        ...
        # raise NotImplementedError

    def update_env(self) -> None:
        """Update the environment settings for the application.

        This updates the environment settings by removing unnecessary
        variables and inserting user-defined UWSGI settings if
        specified.
        """
        from hop3.orm import App  # noqa: PLC0415 - Avoid circular import

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
        """Write configuration settings to a file and enable them by copying to
        another directory.

        This generates a filename based on the application name, type,
        and an ordinal number, writes the settings to a file in the
        'UWSGI_AVAILABLE' directory, and then copies this file to the
        'UWSGI_ENABLED' directory to make the settings active.
        """
        name = f"{self.app_name:s}_{self.kind:s}.{self.ordinal:d}.ini"
        uwsgi_available_path = c.UWSGI_AVAILABLE / name
        uwsgi_enabled_path = c.UWSGI_ENABLED / name
        self.settings.write(uwsgi_available_path)
        shutil.copyfile(uwsgi_available_path, uwsgi_enabled_path)

    def log(self, message) -> None:
        """Logs a formatted message with a specified log level and color.

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
        self.settings += [
            ("module", self.command),
            ("threads", self.env.get("UWSGI_THREADS", "4")),
        ]

        # Only add plugin directive for system-packaged uWSGI (apt/yum)
        # pip-installed uWSGI has Python built-in and doesn't need it
        if _needs_python_plugin():
            self.settings.add("plugin", "python3")

        if "UWSGI_ASYNCIO" in self.env:
            try:
                tasks = int(self.env["UWSGI_ASYNCIO"])
                self.settings += [
                    ("async", tasks),
                ]
                self.log(f"uwsgi will support {tasks} async tasks")
            except ValueError:
                msg = "Error: malformed setting 'UWSGI_ASYNCIO'."
                raise Abort(msg)

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
        """Update the settings by adding the command to the 'attach-daemon'
        section.

        This modifies the current settings to include the specified
        command associated with the key 'attach-daemon'.

        Commands are wrapped in 'sh -c' to enable shell variable expansion
        (e.g., $PORT) which is standard for Heroku-style Procfiles.
        """
        from hop3.orm import App  # noqa: PLC0415 - Avoid circular import

        app = App(name=self.app_name)

        # Build PATH with virtualenv bin directory first
        venv_bin = app.virtualenv_path / "bin"
        path_dirs = [
            str(venv_bin),
            "/usr/local/sbin",
            "/usr/local/bin",
            "/usr/sbin",
            "/usr/bin",
        ]
        path_value = ":".join(path_dirs)

        # Build exports for ALL environment variables
        # uWSGI's attach-daemon spawns a subprocess that doesn't inherit
        # env vars from the uWSGI config, so we must export them explicitly
        exports = [f"export PATH={path_value}"]
        for key, value in self.env.items():
            # Skip keys that shouldn't be exported or are already handled
            if key in {"NGINX_ACL", "PATH"}:
                continue
            # Escape single quotes in values for shell safety
            safe_value = str(value).replace("'", "'\\''")
            exports.append(f"export {key}='{safe_value}'")

        # Wrap command in shell with all exports
        exports_str = "; ".join(exports)
        shell_cmd = f'sh -c "{exports_str}; {self.command}"'
        self.settings.add("attach-daemon", shell_cmd)


@dataclass
class GenericWorker(UwsgiWorker):
    kind: str = "generic"

    def update_settings(self) -> None:
        from hop3.orm import App  # noqa: PLC0415 - Avoid circular import

        app = App(name=self.app_name)

        # Build PATH with virtualenv bin directory first
        venv_bin = app.virtualenv_path / "bin"
        path_dirs = [
            str(venv_bin),
            "/usr/local/sbin",
            "/usr/local/bin",
            "/usr/sbin",
            "/usr/bin",
        ]
        path_value = ":".join(path_dirs)

        # Build exports for ALL environment variables
        # uWSGI's attach-daemon spawns a subprocess that doesn't inherit
        # env vars from the uWSGI config, so we must export them explicitly
        exports = [f"export PATH={path_value}"]
        for key, value in self.env.items():
            # Skip keys that shouldn't be exported or are already handled
            if key in {"NGINX_ACL", "PATH"}:
                continue
            # Escape single quotes in values for shell safety
            safe_value = str(value).replace("'", "'\\''")
            exports.append(f"export {key}='{safe_value}'")

        # Wrap command in shell with all exports
        exports_str = "; ".join(exports)
        shell_cmd = f'sh -c "{exports_str}; {self.command}"'
        self.settings.add("attach-daemon", shell_cmd)
