# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

from hop3.config import UWSGI_ENABLED
from hop3.core.protocols import (
    BuildArtifact,
    DeploymentContext,
    DeploymentInfo,
    DeploymentStrategy,
)
from hop3.lib import log
from hop3.orm import App, AppStateEnum
from hop3.project.procfile import parse_procfile
from hop3.run.spawn import spawn_app


class UWSGIDeployer(DeploymentStrategy):
    """The default deployment strategy, using uWSGI."""

    name = "uwsgi"

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
        # Accept virtualenv (Python, Ruby), node, and buildpack artifacts
        return self.artifact.kind in {
            "buildpack",
            "virtualenv",
            "node",
            "ruby",
            "php",
            "clojure",
            "rust",
            "go",
        }

    def deploy(self, deltas: dict[str, int] | None = None) -> DeploymentInfo:
        """Deploy the app using uWSGI."""
        deltas = deltas or {}

        log(f"Deploying '{self.app.name}' with uWSGI...", level=2, fg="blue")

        # Use state machine transition
        if self.app.run_state == AppStateEnum.STOPPED:
            self.app._transition_state(AppStateEnum.STARTING)  # noqa: SLF001

        spawn_app(self.app, deltas)

        # Mark the app as RUNNING using state machine
        self.app._transition_state(AppStateEnum.RUNNING)  # noqa: SLF001

        # A more robust implementation would get this info from nginx/spawn logic
        return DeploymentInfo(
            protocol="unix_socket", address=f"/path/to/{self.app.name}.sock"
        )

    def start(self) -> None:
        """Starts the app by calling deploy with no scaling changes."""
        log(f"Starting '{self.app.name}' with uWSGI...", level=2, fg="blue")
        # For uWSGI, starting is the same as deploying the current state.
        self.deploy({})

    def stop(self) -> None:
        """Stops the app by removing its uWSGI .ini files from the enabled directory."""
        log(f"Stopping '{self.app.name}'...", level=2, fg="yellow")

        # Use state machine transition: RUNNING -> STOPPING
        if self.app.run_state == AppStateEnum.RUNNING:
            self.app._transition_state(AppStateEnum.STOPPING)  # noqa: SLF001

        config_files = list(UWSGI_ENABLED.glob(f"{self.app.name}*.ini"))
        if not config_files:
            log(f"App '{self.app.name}' is already stopped or not deployed.", level=3)
            # If already stopped in filesystem, ensure DB state matches
            if self.app.run_state != AppStateEnum.STOPPED:
                self.app._transition_state(AppStateEnum.STOPPED)  # noqa: SLF001
            return

        for config_file in config_files:
            config_file.unlink()

        # Complete transition: STOPPING -> STOPPED
        self.app._transition_state(AppStateEnum.STOPPED)  # noqa: SLF001
        log(f"App '{self.app.name}' stopped.", level=2, fg="green")

    def restart(self) -> None:
        """For uWSGI, touching the .ini files is the most efficient way to restart."""
        log(f"Restarting '{self.app.name}'...", level=2, fg="blue")

        config_files = list(UWSGI_ENABLED.glob(f"{self.app.name}*.ini"))
        if not config_files:
            log(
                f"App '{self.app.name}' not running, cannot restart. Starting instead.",
                level=3,
            )
            self.start()
            return

        for config_file in config_files:
            # The uWSGI emperor will see the file modification and restart the vassal.
            config_file.touch()

        log(f"App '{self.app.name}' restart triggered.", level=2, fg="green")

    def destroy(self) -> None:
        """Destruction is a superset of stop."""
        self.stop()
        # Other runtime resource cleanup specific to uWSGI could go here,
        # but most is covered by the file-based approach.

    def scale(self, deltas: dict[str, int] | None = None) -> None:
        """Scaling is a specific type of deployment."""
        deltas = deltas or {}
        log(f"Scaling '{self.app.name}' with deltas: {deltas}", level=2, fg="blue")
        # For uWSGI, scaling is the same as re-deploying with new deltas
        self.deploy(deltas)

    def get_status(self) -> dict:
        """Gets process status from the SCALING file."""
        status = {
            "running": self.app.run_state == AppStateEnum.RUNNING,
            "processes": {},
        }

        scaling_file = self.app.virtualenv_path / "SCALING"
        if scaling_file.exists():
            worker_map = parse_procfile(scaling_file)
            status["processes"] = {k: int(v) for k, v in worker_map.items()}

        return status
