# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Deployment strategy for static file applications."""

from __future__ import annotations

import os

from hop3.config import HOP3_ROOT, HOP3_USER
from hop3.core.env import Env
from hop3.core.plugins import get_proxy_strategy
from hop3.core.protocols import (
    BuildArtifact,
    Deployer,
    DeploymentContext,
    DeploymentInfo,
)
from hop3.lib import log
from hop3.orm import App, AppStateEnum
from hop3.project.config import AppConfig


class StaticDeployer(Deployer):
    """Deployment strategy for static file applications.

    Static apps don't require any runtime process - they're served directly by nginx.
    """

    name = "static"

    def __init__(self, context: DeploymentContext, artifact: BuildArtifact):
        self.context = context
        self.artifact = artifact

    @property
    def app(self) -> App:
        """Get the app from the context."""
        if self.context.app is None:
            msg = "App not provided in deployment context"
            raise RuntimeError(msg)
        return self.context.app

    def accept(self) -> bool:
        """Accept only static artifacts."""
        return self.artifact.kind == "static"

    def _make_env(self) -> Env:
        """Create environment for nginx configuration.

        Similar to AppLauncher.make_env() but simplified for static apps.
        """
        app_config = AppConfig.from_dir(self.app.app_path)
        virtualenv_path = self.app.virtualenv_path

        # Bootstrap environment
        env = Env({
            "APP": self.app.name,
            "HOME": HOP3_ROOT,
            "USER": HOP3_USER,
            "PATH": f"{virtualenv_path / 'bin'}:{os.environ['PATH']}",
            "PWD": str(self.app.app_path),
            "VIRTUAL_ENV": str(virtualenv_path),
        })

        safe_defaults = {
            "NGINX_IPV4_ADDRESS": "0.0.0.0",
            "NGINX_IPV6_ADDRESS": "[::]",
            "BIND_ADDRESS": "127.0.0.1",
            "PORT": "0",  # Dummy port for static apps (not used, but needed by nginx setup)
            "HOST_NAME": "_",  # Catch-all server name for development
        }

        # Load environment variables from the ORM
        runtime_env = self.app.get_runtime_env()
        env.update(runtime_env)

        # Handle IPv6
        if env.get_bool("DISABLE_IPV6"):
            safe_defaults.pop("NGINX_IPV6_ADDRESS", None)
            log("nginx will NOT use IPv6", level=3)

        # Safe defaults for addressing
        for k, v in safe_defaults.items():
            if k not in env:
                log(f"nginx {k:s} will be set to {v}", level=3)
                env[k] = v

        # NOTE: We don't set NGINX_STATIC_PATHS here because the nginx setup
        # will automatically handle it from the "static" worker in the Procfile.
        # The worker path ("public") gets resolved relative to src_path by nginx setup.

        return env

    def deploy(self, deltas: dict[str, int] | None = None) -> DeploymentInfo:
        """Deploy the static app.

        For static apps, deployment just means marking them as RUNNING.
        Nginx will serve the files directly from the artifact location.
        """
        log(f"Deploying static app '{self.app.name}'...", level=2, fg="blue")

        current_state = self.app.run_state

        # Handle redeployment: if already running, just update nginx config
        if current_state == AppStateEnum.RUNNING:
            log(
                f"App '{self.app.name}' is running, updating configuration...",
                level=1,
                fg="blue",
            )
        else:
            # Use state machine transition for initial deployment
            # STOPPED -> STARTING -> RUNNING
            if current_state == AppStateEnum.STOPPED:
                self.app._transition_state(AppStateEnum.STARTING)  # noqa: SLF001
            self.app._transition_state(AppStateEnum.RUNNING)  # noqa: SLF001

        # Set up nginx configuration for static file serving
        env = self._make_env()
        if "HOST_NAME" in env:
            app_config = AppConfig.from_dir(self.app.app_path)
            workers = app_config.workers

            log(
                f"Setting up proxy for static app '{self.app.name}'...",
                level=2,
                fg="blue",
            )
            proxy = get_proxy_strategy(self.app, env, workers)
            proxy.setup()

        # Return deployment info (nginx will serve from static_path)
        static_path = self.artifact.location
        return DeploymentInfo(
            protocol="static",
            address=static_path,
        )

    def start(self) -> None:
        """Start the static app (same as deploy)."""
        log(f"Starting static app '{self.app.name}'...", level=2, fg="blue")
        self.deploy({})

    def stop(self) -> None:
        """Stop the static app."""
        log(f"Stopping static app '{self.app.name}'...", level=2, fg="yellow")
        # Use state machine transition: RUNNING -> STOPPING -> STOPPED
        if self.app.run_state == AppStateEnum.RUNNING:
            self.app._transition_state(AppStateEnum.STOPPING)  # noqa: SLF001
        self.app._transition_state(AppStateEnum.STOPPED)  # noqa: SLF001
        log(f"Static app '{self.app.name}' stopped.", level=2, fg="green")

    def restart(self) -> None:
        """Restart the static app (no-op for static files)."""
        log(f"Restarting static app '{self.app.name}'...", level=2, fg="blue")
        # For static apps, there's nothing to restart - just ensure it's running
        if self.app.run_state != AppStateEnum.RUNNING:
            self.start()
        else:
            log(f"Static app '{self.app.name}' already running.", level=2, fg="green")

    def destroy(self) -> None:
        """Destroy the static app deployment."""
        self.stop()

    def scale(self, deltas: dict[str, int] | None = None) -> None:
        """Scaling is not applicable for static apps."""
        log(
            f"Scaling not applicable for static app '{self.app.name}'",
            level=2,
            fg="yellow",
        )

    def check_status(self) -> bool:
        """Check if the static app is running.

        Static apps don't have processes to check - they're served directly by nginx.
        Once deployed, they're immediately available (nginx serves files from disk).

        Returns:
            True always, since static apps are always "running" after deployment.
        """
        # Static apps have no processes to check - they're served directly by nginx.
        # Once the nginx config is in place, they're considered running.
        # Return True to indicate immediate availability after deployment.
        return True

    def get_status(self) -> dict:
        """Get the status of the static app."""
        return {
            "running": self.app.run_state == AppStateEnum.RUNNING,
            "processes": {},  # No processes for static files
        }
