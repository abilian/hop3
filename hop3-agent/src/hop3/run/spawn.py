# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from click import secho as echo

from hop3.core.env import Env
from hop3.project.config import AppConfig
from hop3.project.procfile import parse_procfile
from hop3.proxies.nginx import setup_nginx
from hop3.system.constants import APP_ROOT, ENV_ROOT, LOG_ROOT, UWSGI_ENABLED
from hop3.system.state import state
from hop3.util import get_free_port
from hop3.util.console import log
from hop3.util.settings import write_settings

from .uwsgi import spawn_uwsgi_worker


def spawn_app(app_name: str, deltas: dict[str, int] | None = None) -> None:
    """Create all workers for an app."""
    launcher = AppLauncher(app_name, deltas)
    launcher.spawn_app()


@dataclass
class AppLauncher:
    app_name: str
    deltas: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        assert isinstance(self.app_name, str)
        assert isinstance(self.deltas, dict)

        self.app_path = Path(APP_ROOT, self.app_name)
        self.virtualenv_path = Path(ENV_ROOT, self.app_name)
        self.config = AppConfig.from_dir(self.app_path)
        self.env = self.make_env()

    @property
    def workers(self) -> dict:
        return self.config.workers

    @property
    def web_workers(self):
        return self.config.web_workers

    def spawn_app(self) -> None:
        """Create the app's workers."""
        # Set up nginx if we have NGINX_SERVER_NAME set
        if "NGINX_SERVER_NAME" in self.env:
            setup_nginx(self.app_name, self.env, self.workers)

        # Configured worker count
        web_worker_count = dict.fromkeys(self.web_workers.keys(), 1)
        scaling = self.virtualenv_path / "SCALING"
        if scaling.exists():
            web_worker_count.update(
                {
                    worker: int(v)
                    for worker, v in parse_procfile(scaling).items()
                    if worker in self.web_workers
                },
            )

        deltas = self.deltas
        to_create = {}
        to_destroy = {}
        for env_key in web_worker_count:
            to_create[env_key] = range(1, web_worker_count[env_key] + 1)
            if deltas.get(env_key):
                to_create[env_key] = range(
                    1,
                    web_worker_count[env_key] + deltas[env_key] + 1,
                )
                if deltas[env_key] < 0:
                    to_destroy[env_key] = range(
                        web_worker_count[env_key],
                        web_worker_count[env_key] + deltas[env_key],
                        -1,
                    )
                web_worker_count[env_key] += deltas[env_key]

        env = self.env.copy()

        # Cleanup env
        for env_key in list(env.keys()):
            if env_key.startswith("HOP3_INTERNAL_"):
                del env[env_key]

        # Save current settings
        live = Path(ENV_ROOT, self.app_name, "LIVE_ENV")
        write_settings(live, env)

        write_settings(scaling, web_worker_count, ":")

        if env.get_bool("HOP3_AUTO_RESTART", default=True):
            configs = list(Path(UWSGI_ENABLED).glob(f"{self.app_name}*.ini"))
            if configs:
                echo("-----> Removing uwsgi configs to trigger auto-restart.")
                for config in configs:
                    config.unlink()

        self.create_new_workers(to_create, env)
        self.remove_unnecessary_workers(to_destroy)

    def make_env(self) -> Env:
        # Bootstrap environment
        env = Env(
            {
                "APP": self.app_name,
                "LOG_ROOT": LOG_ROOT,
                "HOME": os.environ["HOME"],
                "USER": os.environ["USER"],
                "PATH": f"{self.virtualenv_path / 'bin'}:{os.environ['PATH']}",
                "PWD": str(self.app_path),
                "VIRTUAL_ENV": str(self.virtualenv_path),
            },
        )

        safe_defaults = {
            "NGINX_IPV4_ADDRESS": "0.0.0.0",
            "NGINX_IPV6_ADDRESS": "[::]",
            "BIND_ADDRESS": "127.0.0.1",
        }

        # add node path if present
        node_path = self.virtualenv_path / "node_modules"
        if node_path.exists():
            env["NODE_PATH"] = str(node_path)
            env["PATH"] = f"{node_path / '.bin'}:{os.environ['PATH']}"

        # Load environment variables shipped with repo (if any)
        # Settings shipped with the app
        env_file = self.app_path / "ENV"
        env.parse_settings(env_file)

        env.update(state.get_app_env(self.app_name))

        # Pick a port if none defined
        if "PORT" not in env:
            port = env["PORT"] = str(get_free_port())
            log(f"Picked free port: {port}", level=5)

        if env.get_bool("DISABLE_IPV6"):
            safe_defaults.pop("NGINX_IPV6_ADDRESS", None)
            log("nginx will NOT use IPv6", level=5)

        # Safe defaults for addressing
        for k, v in safe_defaults.items():
            if k not in env:
                log(f"nginx {k:s} will be set to {v}", level=5)
                env[k] = v

        return env

    def create_new_workers(self, to_create, env) -> None:
        # Create new workers
        for kind, v in to_create.items():
            for w in v:
                enabled = Path(UWSGI_ENABLED, f"{self.app_name:s}_{kind:s}.{w:d}.ini")
                if enabled.exists():
                    continue

                log(f"spawning '{self.app_name:s}:{kind:s}.{w:d}'", level=5)
                spawn_uwsgi_worker(self.app_name, kind, self.workers[kind], env, w)

    def remove_unnecessary_workers(self, to_destroy) -> None:
        # Remove unnecessary workers (leave logfiles)
        for k, v in to_destroy.items():
            for w in v:
                enabled = Path(UWSGI_ENABLED, f"{self.app_name:s}_{k:s}.{w:d}.ini")
                if not enabled.exists():
                    continue

                msg = f"terminating '{self.app_name:s}:{k:s}.{w:d}'"
                log(msg, level=5, fg="yellow")
                enabled.unlink()
