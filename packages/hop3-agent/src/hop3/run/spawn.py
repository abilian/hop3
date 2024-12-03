# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from hop3.config import c
from hop3.core.env import Env
from hop3.plugins.nginx import Nginx
from hop3.project.config import AppConfig
from hop3.project.procfile import parse_procfile
from hop3.util import echo, get_free_port, log
from hop3.util.settings import write_settings

from .uwsgi import spawn_uwsgi_worker

if TYPE_CHECKING:
    from hop3.orm.app import App


def spawn_app(app: App, deltas: dict[str, int] | None = None) -> None:
    """Create all workers for an app."""
    if deltas is None:
        deltas = {}
    launcher = AppLauncher(app, deltas)
    launcher.spawn_app()


@dataclass
class AppLauncher:
    app: App
    deltas: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """
        Initialize additional attributes for the application configuration.

        This sets up crucial paths and configuration for the application
        object by extracting necessary details from the `app` object, such as
        application name, paths, and environment settings.
        """
        self.app_name = self.app.name
        self.app_path = self.app.app_path
        self.virtualenv_path = self.app.virtualenv_path
        self.config = AppConfig.from_dir(self.app_path)
        self.env = self.make_env()

    @property
    def workers(self) -> dict:
        return self.config.workers

    @property
    def web_workers(self):
        return self.config.web_workers

    def spawn_app(self) -> None:
        """
        Create the app's workers by setting up web worker configurations and handling
        environment-specific setups, including nginx and uwsgi configurations.
        """

        # Set up nginx if we have NGINX_SERVER_NAME set
        if "NGINX_SERVER_NAME" in self.env:
            nginx = Nginx(self.app, self.env, self.workers)
            nginx.setup()

        # Configured worker count using dict.fromkeys to initialize each key with value 1
        web_worker_count = dict.fromkeys(self.web_workers.keys(), 1)
        scaling = self.virtualenv_path / "SCALING"

        # Check if scaling configuration file exists and update web_worker_count
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

        # Determine workers to create and destroy based on deltas
        for env_key in web_worker_count:
            to_create[env_key] = range(1, web_worker_count[env_key] + 1)
            if deltas.get(env_key):
                to_create[env_key] = range(
                    1,
                    web_worker_count[env_key] + deltas[env_key] + 1,
                )
                # If delta is negative, calculate which workers to destroy
                if deltas[env_key] < 0:
                    to_destroy[env_key] = range(
                        web_worker_count[env_key],
                        web_worker_count[env_key] + deltas[env_key],
                        -1,
                    )
                web_worker_count[env_key] += deltas[env_key]

        env = self.env.copy()

        # Cleanup environment variables that are internal
        for env_key in list(env.keys()):
            if env_key.startswith("HOP3_INTERNAL_"):
                del env[env_key]

        # Save current settings to file

        # app = App(self.app_name)
        app = self.app
        live = app.virtualenv_path / "LIVE_ENV"
        write_settings(live, env)

        # Write worker count settings to scaling file
        write_settings(scaling, web_worker_count, ":")

        # Handle auto-restart via uwsgi if enabled
        if env.get_bool("HOP3_AUTO_RESTART", default=True):
            configs = list(c.UWSGI_ENABLED.glob(f"{self.app_name}*.ini"))
            if configs:
                echo("-----> Removing uwsgi configs to trigger auto-restart.")
                for config in configs:
                    config.unlink()

        # Create new workers and remove unnecessary ones
        self.create_new_workers(to_create, env)
        self.remove_unnecessary_workers(to_destroy)

    def make_env(self) -> Env:
        """
        Set up and configure the environment for the application.

        This prepares the environment by bootstrapping settings such as
        application name, user, path, and virtual environment. It also loads any
        environment variables included with the application and configures defaults
        for server settings like binding addresses and ports.

        Returns:
        - Env: An environment configuration object with various settings for the application.
        """
        # Bootstrap environment
        env = Env(
            {
                "APP": self.app_name,
                # "LOG_ROOT": LOG_ROOT,
                "HOME": c.HOP3_ROOT,
                "USER": c.HOP3_USER,
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

        # Load environment variables from the ORM
        env.update(self.app.get_runtime_env())

        # Pick a port if none defined
        if "PORT" not in env:
            port = env["PORT"] = str(get_free_port())
            log(f"Picked free port: {port}", level=3)

        if env.get_bool("DISABLE_IPV6"):
            safe_defaults.pop("NGINX_IPV6_ADDRESS", None)
            log("nginx will NOT use IPv6", level=3)

        # Safe defaults for addressing
        for k, v in safe_defaults.items():
            if k not in env:
                log(f"nginx {k:s} will be set to {v}", level=3)
                env[k] = v

        return env

    def create_new_workers(self, to_create, env) -> None:
        """
        Creates new workers for the given application.

        This iterates over the types of workers specified in the `to_create` dictionary
        and spawns new workers for each type if they are not already enabled.

        Input:
        - to_create: dict
          A dictionary where keys are worker types and values are lists of worker identifiers
          that need to be created.
        - env: dict
          A dictionary representing the environment variables needed for the worker process.
        """
        # Create new workers
        for kind, v in to_create.items():
            for w in v:
                enabled = c.UWSGI_ENABLED / f"{self.app_name:s}_{kind:s}.{w:d}.ini"
                if enabled.exists():
                    # Skip if the worker configuration already exists
                    continue

                log(f"spawning '{self.app_name:s}:{kind:s}.{w:d}'", level=3)
                spawn_uwsgi_worker(self.app_name, kind, self.workers[kind], env, w)

    def remove_unnecessary_workers(self, to_destroy) -> None:
        """
        Removes unnecessary worker configuration files based on the provided dictionary.

        Input:
        - to_destroy: A dictionary where keys are worker types (as strings) and values are
          lists of worker identifiers (as integers) that need to be removed.
        """
        # Remove unnecessary workers (leave logfiles)
        for k, v in to_destroy.items():
            for w in v:
                enabled = c.UWSGI_ENABLED / f"{self.app_name:s}_{k:s}.{w:d}.ini"
                if not enabled.exists():
                    continue  # Skip if the file does not exist

                # Log the termination message with a specific log level and color
                msg = f"terminating '{self.app_name:s}:{k:s}.{w:d}'"
                log(msg, level=3, fg="yellow")
                enabled.unlink()  # Remove the worker's configuration file
