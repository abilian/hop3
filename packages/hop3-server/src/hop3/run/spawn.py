# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
import subprocess
import time
import traceback
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy.orm import object_session

from hop3.config import HOP3_ROOT, HOP3_USER, UWSGI_ENABLED
from hop3.core.env import Env
from hop3.core.plugins import get_proxy_strategy
from hop3.lib import echo, get_free_port, log
from hop3.lib.logging import server_log
from hop3.lib.settings import write_settings
from hop3.project.config import AppConfig
from hop3.project.procfile import parse_procfile

from .uwsgi import spawn_uwsgi_worker

if TYPE_CHECKING:
    from hop3.orm import App


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
        """Initialize additional attributes for the application configuration.

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

    def _update_app_metadata(self, host_name: str) -> None:
        """Update app model with port and hostname, persisting to database."""
        if "PORT" in self.env:
            self.app.port = int(self.env["PORT"])

        if host_name and host_name != "_":
            self.app.hostname = host_name

        session = object_session(self.app)
        if session:
            session.commit()

    def _setup_proxy(self, host_name: str) -> None:
        """Setup proxy configuration.

        Apps without a configured hostname don't get proxy configuration.
        They remain accessible only via direct port access until a hostname is set.
        """
        if not host_name or host_name == "_":
            log(
                f"Skipping proxy setup for '{self.app_name}' (no HOST_NAME configured)",
                level=2,
                fg="yellow",
            )
            return

        log(
            f"Setting up proxy for '{self.app_name}' with server_name='{host_name}'",
            level=1,
            fg="green",
        )
        try:
            proxy = get_proxy_strategy(self.app, self.env, self.workers)
            proxy.setup()
            log(
                f"✓ Proxy setup completed for '{self.app_name}'",
                level=0,
                fg="green",
            )
        except Exception as e:
            log(
                f"✗ Proxy setup failed for '{self.app_name}': {e}",
                level=0,
                fg="red",
            )
            server_log.exception(
                "Proxy setup failed", app_name=self.app_name, error=str(e)
            )
            traceback.print_exc()

    def _calculate_worker_changes(self, worker_count: dict) -> tuple[dict, dict]:
        """Calculate which workers to create and destroy based on deltas.

        Returns:
            Tuple of (to_create, to_destroy) dictionaries
        """
        to_create = {}
        to_destroy = {}

        for env_key in worker_count:
            to_create[env_key] = range(1, worker_count[env_key] + 1)
            if self.deltas.get(env_key):
                to_create[env_key] = range(
                    1,
                    worker_count[env_key] + self.deltas[env_key] + 1,
                )
                if self.deltas[env_key] < 0:
                    to_destroy[env_key] = range(
                        worker_count[env_key],
                        worker_count[env_key] + self.deltas[env_key],
                        -1,
                    )
                worker_count[env_key] += self.deltas[env_key]

        return to_create, to_destroy

    def _get_worker_counts(self, scaling) -> dict:
        """Get worker counts from configuration and scaling file.

        This includes ALL workers from the Procfile (web, worker, etc.),
        not just web workers.
        """
        # Use all workers, not just web_workers
        worker_count = dict.fromkeys(self.workers.keys(), 1)

        if scaling.exists():
            worker_count.update(
                {
                    worker: int(v)
                    for worker, v in parse_procfile(scaling).items()
                    if worker in self.workers
                },
            )
        return worker_count

    def _prepare_environment(self) -> Env:
        """Prepare environment by removing internal variables."""
        env = self.env.copy()
        for env_key in list(env.keys()):
            if env_key.startswith("HOP3_INTERNAL_"):
                del env[env_key]
        return env

    def _handle_auto_restart(self, env: Env) -> None:
        """Handle auto-restart by removing uwsgi configs if enabled."""
        if env.get_bool("HOP3_AUTO_RESTART", default=True):
            configs = list(UWSGI_ENABLED.glob(f"{self.app_name}*.ini"))
            if configs:
                echo("-----> Removing uwsgi configs to trigger auto-restart.")
                for config in configs:
                    config.unlink()
                # Wait for uwsgi emperor to fully terminate old processes
                # before creating new configs. Without this wait, old gunicorn
                # workers may still be running and holding resources when new
                # workers are spawned, causing the new workers to deadlock.
                self._wait_for_old_processes_to_terminate()
                # Clean up stale socket files that may have been left behind
                self._cleanup_stale_sockets()

    def _wait_for_old_processes_to_terminate(self, timeout: float = 10.0) -> None:
        """Wait for old app processes to terminate after config removal.

        The uwsgi emperor monitors config files and sends SIGTERM to vassals
        when their configs are removed. We need to wait for the old processes
        to fully terminate before creating new configs, otherwise the new
        gunicorn workers may deadlock.
        """
        start_time = time.time()
        check_interval = 0.5
        processes_found = False

        while time.time() - start_time < timeout:
            # Check if any gunicorn or uwsgi processes for this app are still running
            try:
                result = subprocess.run(
                    ["pgrep", "-f", f"apps/{self.app_name}"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode != 0:
                    # No processes found
                    if processes_found:
                        # Processes were found earlier, now they're gone
                        log(f"Old processes for '{self.app_name}' terminated", level=3)
                        # Add a small grace period for file descriptors to close
                        time.sleep(1)
                    return
                processes_found = True
            except (subprocess.TimeoutExpired, FileNotFoundError):
                # pgrep not available or timed out, fall back to fixed delay
                break

            time.sleep(check_interval)

        # Timeout reached or pgrep unavailable - use a fixed delay as fallback
        remaining = timeout - (time.time() - start_time)
        if remaining > 0:
            log(
                f"Waiting {remaining:.1f}s for old processes to terminate",
                level=3,
                fg="yellow",
            )
            time.sleep(remaining)

    def _cleanup_stale_sockets(self) -> None:
        """Clean up stale socket files left behind by previous processes.

        Gunicorn creates a control socket (gunicorn.ctl) in the working directory.
        When the process is killed, this socket file may persist and cause the
        new gunicorn process to hang during startup.
        """

        src_path = self.app_path / "src"
        if not src_path.exists():
            return

        # Clean up gunicorn control sockets
        for socket_file in src_path.glob("*.ctl"):
            try:
                if socket_file.is_socket():
                    socket_file.unlink()
                    log(f"Removed stale socket: {socket_file.name}", level=3)
            except OSError:
                pass  # Socket might be in use or already gone

        # Also clean up any .sock files
        for socket_file in src_path.glob("*.sock"):
            try:
                if socket_file.is_socket():
                    socket_file.unlink()
                    log(f"Removed stale socket: {socket_file.name}", level=3)
            except OSError:
                pass

    def spawn_app(self) -> None:
        """Create the app's workers by setting up web worker configurations and
        handling environment-specific setups, including nginx and uwsgi
        configurations."""
        server_log.info(
            "Spawning app workers",
            app_name=self.app_name,
            workers=list(self.workers.keys()),
        )

        host_name = self.env.get("HOST_NAME", "")
        self._update_app_metadata(host_name)
        self._setup_proxy(host_name)

        scaling = self.virtualenv_path / "SCALING"
        worker_count = self._get_worker_counts(scaling)
        to_create, to_destroy = self._calculate_worker_changes(worker_count)

        env = self._prepare_environment()

        # Save current settings to file
        live = self.app.virtualenv_path / "LIVE_ENV"
        write_settings(live, env)
        write_settings(scaling, worker_count, ":")

        self._handle_auto_restart(env)

        # Create new workers and remove unnecessary ones
        self.create_new_workers(to_create, env)
        self.remove_unnecessary_workers(to_destroy)

    def _setup_node_paths(self, env: Env) -> None:
        """Add Node.js paths to environment if node_modules exists."""
        # Check both venv and src directories
        # For Node apps built from source, node_modules is in src/
        # For apps using nodeenv, node_modules might be in venv/
        for node_path in [
            self.app.src_path / "node_modules",
            self.virtualenv_path / "node_modules",
        ]:
            if node_path.exists():
                if "NODE_PATH" not in env:
                    env["NODE_PATH"] = str(node_path)
                # Prepend node_modules/.bin to existing PATH (not os.environ)
                node_bin = str(node_path / ".bin")
                if node_bin not in env["PATH"]:
                    env["PATH"] = f"{node_bin}:{env['PATH']}"
                break  # Use the first node_modules found

    def _setup_ruby_paths(self, env: Env) -> None:
        """Add Ruby gem paths to environment if Gemfile exists."""
        gemfile = self.app.src_path / "Gemfile"
        if gemfile.exists():
            env["BUNDLE_PATH"] = str(self.virtualenv_path)
            env["GEM_HOME"] = str(self.virtualenv_path)
            # Add gem bin directory to PATH for gem executables (bundle, puma, etc.)
            gem_bin = self.virtualenv_path / "bin"
            if gem_bin.exists() and str(gem_bin) not in env["PATH"]:
                env["PATH"] = f"{gem_bin}:{env['PATH']}"

    def _setup_python_paths(self, env: Env) -> None:
        """Add src/ to PYTHONPATH for Python apps with src layout.

        This is a common pattern where packages live in src/package_name/
        (e.g., Poetry projects with packages = [{ include = "app", from = "src" }])
        """
        src_dir = self.app.src_path / "src"
        if src_dir.is_dir():
            existing_pythonpath = env.get("PYTHONPATH", "")
            if existing_pythonpath:
                env["PYTHONPATH"] = f"{src_dir}:{existing_pythonpath}"
            else:
                env["PYTHONPATH"] = str(src_dir)
            log("Added src/ to PYTHONPATH for src-layout app", level=3)

    def make_env(self) -> Env:
        """Set up and configure the environment for the application.

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
                "HOME": HOP3_ROOT,
                "USER": HOP3_USER,
                "PATH": f"{self.virtualenv_path / 'bin'}:{os.environ['PATH']}",
                "PWD": str(self.app_path),
                "VIRTUAL_ENV": str(self.virtualenv_path),
            },
        )

        safe_defaults = {
            "NGINX_IPV4_ADDRESS": "0.0.0.0",
            "NGINX_IPV6_ADDRESS": "[::]",
            "BIND_ADDRESS": "127.0.0.1",
            # No default HOST_NAME - apps without hostname don't get proxy config
        }

        # Add language-specific paths
        self._setup_node_paths(env)
        self._setup_ruby_paths(env)
        self._setup_python_paths(env)

        # Load environment variables from the ORM
        runtime_env = self.app.get_runtime_env()
        env.update(runtime_env)
        server_log.info(
            "Loaded runtime env_vars from ORM",
            app_name=self.app_name,
            env_vars_count=len(runtime_env),
            env_vars_keys=list(runtime_env.keys()),
        )

        # Always pick a fresh port for each deployment
        # The uwsgi configs are removed by _handle_auto_restart and recreated,
        # so nginx and uwsgi will always be in sync with the same port
        if "PORT" not in env:
            port = env["PORT"] = str(get_free_port())
            log(f"Picked free port: {port}", level=3)

        if env.get_bool("DISABLE_IPV6"):
            safe_defaults.pop("NGINX_IPV6_ADDRESS", None)
            log("nginx will NOT use IPv6", level=3)

        # Safe defaults for addressing
        for k, v in safe_defaults.items():
            if k not in env:
                env[k] = v

        return env

    def create_new_workers(self, to_create, env) -> None:
        """Creates new workers for the given application.

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
                enabled = UWSGI_ENABLED / f"{self.app_name:s}_{kind:s}.{w:d}.ini"
                if enabled.exists():
                    # Skip if the worker configuration already exists
                    continue

                log(f"spawning '{self.app_name:s}:{kind:s}.{w:d}'", level=3)
                spawn_uwsgi_worker(self.app_name, kind, self.workers[kind], env, w)

    def remove_unnecessary_workers(self, to_destroy) -> None:
        """Removes unnecessary worker configuration files based on the provided
        dictionary.

        Input:
        - to_destroy: A dictionary where keys are worker types (as strings) and values are
          lists of worker identifiers (as integers) that need to be removed.
        """
        # Remove unnecessary workers (leave logfiles)
        for k, v in to_destroy.items():
            for w in v:
                enabled = UWSGI_ENABLED / f"{self.app_name:s}_{k:s}.{w:d}.ini"
                if not enabled.exists():
                    continue  # Skip if the file does not exist

                # Log the termination message with a specific log level and color
                msg = f"terminating '{self.app_name:s}:{k:s}.{w:d}'"
                log(msg, level=3, fg="yellow")
                enabled.unlink()  # Remove the worker's configuration file
