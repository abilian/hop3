# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from click import secho as echo
from devtools import debug

from hop3.core.env import Env
from hop3.nginx import setup_nginx
from hop3.project.config import Config
from hop3.project.procfile import parse_procfile
from hop3.run.uwsgi import spawn_uwsgi_worker
from hop3.system.constants import APP_ROOT, ENV_ROOT, LOG_ROOT, UWSGI_ENABLED
from hop3.util import get_free_port
from hop3.util.console import log
from hop3.util.settings import parse_settings, write_settings


def spawn_app(app_name: str, deltas: dict[str, int] | None = None) -> None:
    """Create all workers for an app"""

    launcher = AppLauncher(app_name, deltas)
    launcher.spawn_app()


@dataclass
class AppLauncher:
    app_name: str
    deltas: dict[str, int] = field(default_factory=dict)

    def __post_init__(self):
        self.app_path = Path(APP_ROOT, self.app_name)
        self.config = Config.from_dir(self.app_path)
        self.workers = self.config.web_workers
        self.env = self.get_env()

    def spawn_app(self):
        """Create the app's workers"""

        # Set up nginx if we have NGINX_SERVER_NAME set
        if "NGINX_SERVER_NAME" in self.env:
            debug(self.env)
            setup_nginx(self.app_name, self.env, self.workers)

        # Configured worker count
        worker_count = {k: 1 for k in self.workers.keys()}
        scaling = Path(ENV_ROOT, self.app_name, "SCALING")
        if scaling.exists():
            worker_count.update(
                {
                    worker: int(v)
                    for worker, v in parse_procfile(scaling).items()
                    if worker in self.workers
                }
            )

        deltas = self.deltas
        to_create = {}
        to_destroy = {}
        for env_key in worker_count.keys():
            to_create[env_key] = range(1, worker_count[env_key] + 1)
            if env_key in deltas and deltas[env_key]:
                to_create[env_key] = range(
                    1, worker_count[env_key] + deltas[env_key] + 1
                )
                if deltas[env_key] < 0:
                    to_destroy[env_key] = range(
                        worker_count[env_key],
                        worker_count[env_key] + deltas[env_key],
                        -1,
                    )
                worker_count[env_key] += deltas[env_key]

        env = self.env.copy()

        # Cleanup env
        for env_key in list(env.keys()):
            if env_key.startswith("HOP3_INTERNAL_"):
                del env[env_key]

        # Save current settings
        live = Path(ENV_ROOT, self.app_name, "LIVE_ENV")
        write_settings(live, env)

        write_settings(scaling, worker_count, ":")

        if env.get_bool("HOP3_AUTO_RESTART", True):
            configs = list(Path(UWSGI_ENABLED).glob(f"{self.app_name}*.ini"))
            if len(configs):
                echo("-----> Removing uwsgi configs to trigger auto-restart.")
                for config in configs:
                    config.unlink()

        self.create_new_workers(to_create, env)
        self.remove_unnecessary_workers(to_destroy)

    def get_env(self):
        # the Python virtualenv
        virtualenv_path = Path(ENV_ROOT, self.app_name)

        # Settings shipped with the app
        env_file = Path(APP_ROOT, self.app_name, "ENV")

        # Custom overrides
        settings = Path(ENV_ROOT, self.app_name, "ENV")

        # Bootstrap environment
        env = Env(
            {
                "APP": self.app_name,
                "LOG_ROOT": LOG_ROOT,
                "HOME": os.environ["HOME"],
                "USER": os.environ["USER"],
                "PATH": f"{virtualenv_path / 'bin'}:{os.environ['PATH']}",
                "PWD": str(self.app_path),
                "VIRTUAL_ENV": str(virtualenv_path),
            }
        )

        safe_defaults = {
            "NGINX_IPV4_ADDRESS": "0.0.0.0",
            "NGINX_IPV6_ADDRESS": "[::]",
            "BIND_ADDRESS": "127.0.0.1",
        }

        # add node path if present
        node_path = Path(virtualenv_path, "node_modules")
        if node_path.exists():
            env["NODE_PATH"] = str(node_path)
            env["PATH"] = f"{node_path / '.bin'}:{os.environ['PATH']}"

        # Load environment variables shipped with repo (if any)
        if env_file.exists():
            env.update(parse_settings(env_file, env))

        # Override with custom settings (if any)
        if settings.exists():
            env.update(parse_settings(settings, env))

        # Pick a port if none defined
        if "PORT" not in env:
            port = env["PORT"] = str(get_free_port())
            log(f"Picking free port {port}", level=5)

        if env.get_bool("DISABLE_IPV6"):
            safe_defaults.pop("NGINX_IPV6_ADDRESS", None)
            log("nginx will NOT use IPv6", level=5)

        # Safe defaults for addressing
        for k, v in safe_defaults.items():
            if k not in env:
                log(f"nginx {k:s} will be set to {v}", level=5)
                env[k] = v

        return env

    def create_new_workers(self, to_create, env):
        # Create new workers
        for kind, v in to_create.items():
            for w in v:
                enabled = Path(UWSGI_ENABLED, f"{self.app_name:s}_{kind:s}.{w:d}.ini")
                if not enabled.exists():
                    log(
                        f"spawning '{self.app_name:s}:{kind:s}.{w:d}'",
                        level=5,
                        fg="green",
                    )
                    spawn_uwsgi_worker(self.app_name, kind, self.workers[kind], env, w)

    def remove_unnecessary_workers(self, to_destroy):
        # Remove unnecessary workers (leave logfiles)
        for k, v in to_destroy.items():
            for w in v:
                enabled = Path(UWSGI_ENABLED, f"{self.app_name:s}_{k:s}.{w:d}.ini")
                if enabled.exists():
                    log(
                        f"terminating '{self.app_name:s}:{k:s}.{w:d}'",
                        level=5,
                        fg="yellow",
                    )
                    enabled.unlink()
