# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

import socket
import subprocess
from dataclasses import dataclass

from hop3.config import UWSGI_ENABLED, HopConfig
from hop3.core.protocols import (
    BuildArtifact,
    DeploymentContext,
    DeploymentInfo,
)
from hop3.lib import log
from hop3.orm import App, AppStateEnum
from hop3.project.procfile import parse_procfile
from hop3.run.reaper import (
    GRACEFUL_STOP_SECONDS,
    app_pids,
    proc_belongs_to_app,
    reap_app_processes,
)
from hop3.run.spawn import spawn_app

# Process detection/reaping moved to hop3.run.reaper so the ORM teardown
# (app.stop()/destroy()) shares it. Keep this name importable here for tests.
_proc_belongs_to_app = proc_belongs_to_app
_GRACEFUL_STOP_SECONDS = GRACEFUL_STOP_SECONDS


@dataclass(frozen=True)
class UWSGIDeployer:
    """The default deployment strategy, using uWSGI."""

    context: DeploymentContext
    artifact: BuildArtifact
    name: str = "uwsgi"

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
            # Language toolchains
            "python",
            "node",
            "ruby",
            "php",
            "clojure",
            "rust",
            "go",
            "java",
            "dotnet",
            "elixir",
            "generic",  # Pre-built binaries or custom build apps
            # Nix builder
            "nix",
            # Legacy/compatibility
            "buildpack",
            "virtualenv",  # Legacy Python artifact kind
        }

    def deploy(self, deltas: dict[str, int] | None = None) -> DeploymentInfo:
        """
        Deploy the app using uWSGI.

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
            self.app._transition_state(AppStateEnum.STARTING)  # ruff:ignore[private-member-access]

        spawn_app(self.app, deltas)

        # Mark the app as RUNNING (STARTING -> RUNNING)
        # Note: The background state sync service may have already transitioned
        # the app to RUNNING if it detected processes started. Handle gracefully.
        if self.app.run_state != AppStateEnum.RUNNING:
            self.app._transition_state(AppStateEnum.RUNNING)  # ruff:ignore[private-member-access]

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
        """
        Stops the app by removing its uWSGI .ini files from the enabled directory.

        After removing config files, waits for old processes to terminate.
        This ensures the uWSGI Emperor fully cleans up the old vassal,
        including resetting any throttle state from crashed daemons.
        """
        log(f"Stopping '{self.app.name}'...", level=2, fg="yellow")

        # Use state machine transition: RUNNING -> STOPPING
        if self.app.run_state == AppStateEnum.RUNNING:
            self.app._transition_state(AppStateEnum.STOPPING)  # ruff:ignore[private-member-access]

        config_files = list(UWSGI_ENABLED.glob(f"{self.app.name}*.ini"))
        if not config_files:
            log(f"App '{self.app.name}' is already stopped or not deployed.", level=3)
            # If already stopped in filesystem, ensure DB state matches
            if self.app.run_state != AppStateEnum.STOPPED:
                self.app._transition_state(AppStateEnum.STOPPED)  # ruff:ignore[private-member-access]
            return

        for config_file in config_files:
            config_file.unlink()

        # Wait for the Emperor to fully terminate the old vassal processes, then
        # CONFIRM they are gone. This is critical for two reasons: leftover
        # throttle state delays the new vassal, AND a survivor still holding a
        # fixed port (an exec'd Nix daemon) would make the imminent spawn fail
        # to bind. If any survive even SIGKILL, refuse to report STOPPED or let
        # the redeploy spawn on a still-held port.
        survivors = self._wait_for_processes_to_stop()
        if survivors:
            msg = (
                f"Could not stop all processes for '{self.app.name}': "
                f"{len(survivors)} still running (pids {survivors}); the port(s) "
                f"they hold remain in use, so a redeploy would fail to bind."
            )
            raise RuntimeError(msg)

        # Complete transition: STOPPING -> STOPPED
        self.app._transition_state(AppStateEnum.STOPPED)  # ruff:ignore[private-member-access]
        log(f"App '{self.app.name}' stopped.", level=2, fg="green")

    def _app_pids(self) -> list[int]:
        """PIDs of every live process belonging to this app (see hop3.run.reaper)."""
        return app_pids(self.app.name)

    def _wait_for_processes_to_stop(
        self, timeout: float = _GRACEFUL_STOP_SECONDS
    ) -> list[int]:
        """Block until the app's processes are gone; return any survivors."""
        return reap_app_processes(self.app.name, timeout)

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
        """
        Check if the deployed uWSGI application is actually running.

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
