# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

import socket
import subprocess

from hop3.config import UWSGI_ENABLED, HopConfig
from hop3.core.protocols import (
    BuildArtifact,
    Deployer,
    DeploymentContext,
    DeploymentInfo,
)
from hop3.lib import log
from hop3.orm import App, AppStateEnum
from hop3.project.procfile import parse_procfile
from hop3.run.spawn import spawn_app


class UWSGIDeployer(Deployer):
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
        # Accept common artifact kinds from language toolchains
        # Note: "static" is NOT included - static files are handled by StaticDeployer
        return self.artifact.kind in {
            "buildpack",
            "virtualenv",
            "node",
            "ruby",
            "php",
            "clojure",
            "rust",
            "go",
            "java",
            "dotnet",
            "elixir",
        }

    def deploy(self, deltas: dict[str, int] | None = None) -> DeploymentInfo:
        """Deploy the app using uWSGI.

        Handles both fresh deployments and redeployments:
        - STOPPED -> STARTING -> RUNNING (fresh deploy)
        - RUNNING -> STOPPING -> STOPPED -> STARTING -> RUNNING (redeploy)
        """
        deltas = deltas or {}

        current_state = self.app.run_state

        # Handle redeployment: stop first if already running
        if current_state == AppStateEnum.RUNNING:
            log(f"App '{self.app.name}' is running, redeploying...", level=1, fg="blue")
            self.stop()
            current_state = self.app.run_state

        log(f"Deploying '{self.app.name}' with uWSGI...", level=2, fg="blue")

        # Transition to STARTING (handles both STOPPED and FAILED states)
        if current_state in {AppStateEnum.STOPPED, AppStateEnum.FAILED}:
            self.app._transition_state(AppStateEnum.STARTING)  # noqa: SLF001

        spawn_app(self.app, deltas)

        # Mark the app as RUNNING (STARTING -> RUNNING)
        self.app._transition_state(AppStateEnum.RUNNING)  # noqa: SLF001

        # Return HTTP socket info (apps now listen on HTTP ports)
        bind_address = "127.0.0.1"
        port = self.app.port
        return DeploymentInfo(protocol="http", address=bind_address, port=port)

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

    def check_status(self) -> bool:
        """Check if the deployed uWSGI application is actually running.

        Returns:
            True if processes are confirmed running, False otherwise.

        The primary check is whether the app's HTTP port is listening.
        This is the most reliable indicator that the app is actually serving.
        Process checks (pgrep) are only used when no port is assigned.
        """
        cfg = HopConfig.get_instance()

        # Primary check: Is the HTTP port listening?
        # This is the most reliable indicator that the app is actually serving
        if self.app.port:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(1)
                    connect_result = s.connect_ex(("127.0.0.1", self.app.port))
                    # Port is listening (0) = running, otherwise not running
                    # If port is assigned but not listening, app is NOT running properly
                    return connect_result == 0
            except OSError:
                # Socket error - assume not running
                return False

        # No port assigned - fall back to process-based checks
        # This can happen for cron workers or other non-web processes

        # Check for running uWSGI processes with this app's name
        # uWSGI sets procname-prefix to "{app_name}:{kind}:"
        try:
            pgrep_result = subprocess.run(
                ["pgrep", "-f", f"{self.app.name}:"],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
            if pgrep_result.returncode == 0 and pgrep_result.stdout.strip():
                # Found running processes
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # pgrep not available or timed out
            pass

        # Check if config files exist (could be starting up)
        config_files = list(cfg.UWSGI_ENABLED.glob(f"{self.app.name}*.ini"))
        if len(config_files) > 0:
            # Config files exist but no running processes detected
            # Could be starting up or crashed - return False to be conservative
            return False

        # No config files at all
        return False

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
