# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from advanced_alchemy.base import BigIntAuditBase
from sqlalchemy import DateTime, String, TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Integer as SQLInteger

from hop3.config import HopConfig
from hop3.core.env import Env
from hop3.core.plugins import get_deployer_by_name
from hop3.lib import Abort, get_free_port, log
from hop3.run.spawn import spawn_app

if TYPE_CHECKING:
    from .addon_credential import AddonCredential
    from .env import EnvVar


class AppStateEnum(Enum):
    """Enumeration for representing the state of an application.

    States follow a finite state machine with these transitions:
    - STOPPED -> STARTING -> RUNNING
    - RUNNING -> STOPPING -> STOPPED
    - Any state -> FAILED (on error)
    - FAILED -> STOPPED (manual recovery)
    """

    STOPPED = 1  # Application is not running
    STARTING = 2  # Application is starting up (transitional)
    RUNNING = 3  # Application is running normally
    STOPPING = 4  # Application is shutting down (transitional)
    FAILED = 5  # Application failed to start or crashed


class IntEnum(TypeDecorator):
    """Custom type that stores enum values as integers but returns enum objects."""

    impl = SQLInteger
    cache_ok = True

    def __init__(self, enum_class):
        self.enum_class = enum_class
        super().__init__()

    def process_bind_param(self, value, dialect):
        """Convert enum to integer for storage."""
        if value is None:
            return None
        if isinstance(value, self.enum_class):
            return value.value
        return value

    def process_result_value(self, value, dialect):
        """Convert integer to enum when reading."""
        if value is None:
            return None
        # Handle both string and integer values from database
        # SQLite may return strings, so convert to int first
        if isinstance(value, str):
            value = int(value)
        return self.enum_class(value)


# Valid state transitions (from_state -> to_state)
VALID_STATE_TRANSITIONS = {
    AppStateEnum.STOPPED: {AppStateEnum.STARTING, AppStateEnum.FAILED},
    AppStateEnum.STARTING: {AppStateEnum.RUNNING, AppStateEnum.FAILED},
    AppStateEnum.RUNNING: {AppStateEnum.STOPPING, AppStateEnum.FAILED},
    AppStateEnum.STOPPING: {AppStateEnum.STOPPED, AppStateEnum.FAILED},
    AppStateEnum.FAILED: {
        AppStateEnum.STOPPED,
        AppStateEnum.STARTING,
    },  # Manual recovery
}


class StateTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""


class App(BigIntAuditBase):
    """Represents an application with relevant properties such as name, run
    state, and port."""

    __tablename__ = "app"

    name: Mapped[str] = mapped_column(String(128))
    runtime: Mapped[str] = mapped_column(String(64), default="uwsgi")
    run_state: Mapped[AppStateEnum] = mapped_column(
        IntEnum(AppStateEnum), default=AppStateEnum.STOPPED
    )
    port: Mapped[int] = mapped_column(default=0)
    hostname: Mapped[str] = mapped_column(default="")
    error_message: Mapped[str] = mapped_column(String(1024), default="")
    state_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=None, nullable=True
    )
    # Image tag for container-based runtimes (e.g., "hop3/myapp:latest")
    image_tag: Mapped[str] = mapped_column(String(256), default="", nullable=True)
    # Timestamp of last successful deployment (for --since-deploy log filter)
    last_deployed_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=None, nullable=True
    )

    env_vars: Mapped[list[EnvVar]] = relationship(
        back_populates="app", cascade="all, delete-orphan", lazy="selectin"
    )

    addon_credentials: Mapped[list[AddonCredential]] = relationship(
        back_populates="app", cascade="all, delete-orphan", lazy="selectin"
    )

    def check_exists(self) -> None:
        if not (HopConfig.get_instance().APP_ROOT / self.name).exists():
            msg = f"Error: app '{self.name}' not found."
            raise Abort(msg)

    def create(self) -> None:
        self.app_path.mkdir(exist_ok=True)
        # The data directory may already exist, since this may be
        # a full redeployment
        # (we never delete data since it may be expensive to recreate)
        for path in [self.repo_path, self.src_path, self.data_path, self.log_path]:
            path.mkdir(exist_ok=True)

        # log_path = LOG_ROOT / self.app_name
        # if not log_path.exists():
        #     os.makedirs(log_path)

    @property
    def is_running(self) -> bool:
        """Check if app reports as RUNNING in database state."""
        return self.run_state == AppStateEnum.RUNNING

    def check_actual_status(self) -> AppStateEnum:
        """Check the actual running status by delegating to the deployment strategy.

        This method is runtime-agnostic - it delegates the actual status checking
        to the appropriate deployment strategy (uWSGI, Docker, systemd, etc.) based
        on the app's runtime field.

        Returns the actual state based on whether worker processes exist.
        This is used to sync the database state with reality.
        """
        try:
            strategy = get_deployer_by_name(self, self.runtime)
            is_running = strategy.check_status()
            return AppStateEnum.RUNNING if is_running else AppStateEnum.STOPPED
        except (ValueError, RuntimeError) as e:
            # Unknown runtime or error checking status - log and return STOPPED
            log(f"Error checking status for app '{self.name}': {e}", fg="red")
            return AppStateEnum.STOPPED

    def sync_state(self) -> bool:
        """Synchronize database state with actual running status.

        This checks if the app is actually running and updates transitional states
        (STARTING/STOPPING) to their final states (RUNNING/STOPPED).

        Returns:
            True if state was updated, False if no change
        """
        actual_status = self.check_actual_status()
        current_state = self.run_state

        # Only update transitional states
        if current_state == AppStateEnum.STARTING:
            if actual_status == AppStateEnum.RUNNING:
                self._transition_state(AppStateEnum.RUNNING)
                return True
        elif current_state == AppStateEnum.STOPPING:
            if actual_status == AppStateEnum.STOPPED:
                self._transition_state(AppStateEnum.STOPPED)
                return True

        return False

    def wait_for_actual_state(
        self,
        expected_state: AppStateEnum,
        timeout: float = 10.0,
        poll_interval: float = 0.5,
    ) -> bool:
        """Wait for the app to reach the expected actual state.

        Polls check_actual_status() until the expected state is reached or timeout.

        Args:
            expected_state: The state we're waiting for (RUNNING or STOPPED)
            timeout: Maximum seconds to wait (default: 10.0)
            poll_interval: Seconds between status checks (default: 0.5)

        Returns:
            True if the expected state was reached, False if timed out
        """
        deadline = time.time() + timeout

        while time.time() < deadline:
            actual_state = self.check_actual_status()
            if actual_state == expected_state:
                return True
            time.sleep(poll_interval)

        return False

    def _transition_state(self, new_state: AppStateEnum, error_msg: str = "") -> None:
        """Transition to a new state with validation.

        Args:
            new_state: Target state to transition to
            error_msg: Optional error message (for FAILED state)

        Raises:
            StateTransitionError: If the transition is not valid
        """
        current_state = self.run_state
        valid_transitions = VALID_STATE_TRANSITIONS.get(current_state, set())

        if new_state not in valid_transitions:
            # Provide user-friendly error messages for common cases
            if current_state == new_state:
                state_name = current_state.name.lower()
                msg = f"App '{self.name}' is already {state_name}."
            else:
                msg = (
                    f"Cannot transition app '{self.name}' from "
                    f"{current_state.name} to {new_state.name}."
                )
            raise StateTransitionError(msg)

        self.run_state = new_state
        self.state_changed_at = datetime.now(UTC)

        if new_state == AppStateEnum.FAILED:
            self.error_message = error_msg
        else:
            # Clear error message on successful state transitions
            self.error_message = ""

        log(
            f"App '{self.name}' state: {current_state.name} -> {new_state.name}",
            level=2,
            fg="blue",
        )

    #
    # Paths
    #
    @property
    def app_path(self) -> Path:
        """Path to the root directory of the app."""
        return HopConfig.get_instance().APP_ROOT / self.name

    @property
    def repo_path(self) -> Path:
        """Path to the git repository of the app."""
        return self.app_path / "git"

    @property
    def src_path(self) -> Path:
        """Path to the source directory of the app."""
        return self.app_path / "src"

    @property
    def data_path(self) -> Path:
        """Path to the data directory of the app."""
        return self.app_path / "data"

    @property
    def log_path(self) -> Path:
        """Path to the log directory of the app."""
        return self.app_path / "log"

    @property
    def virtualenv_path(self) -> Path:
        """Pathe to the virtualenv of the app."""
        return self.app_path / "venv"

    def get_runtime_env(self) -> Env:
        """Retrieves the runtime environment for the current application.

        This fetches the environment settings for the application
        identified by the instance's name attribute.
        """
        data = {}
        for env_var in self.env_vars:
            data[env_var.name] = env_var.value
        return Env(data)

    def update_runtime_env(self, env: Env) -> None:
        """Updates the runtime environment for the current application.

        This updates the environment settings for the application
        identified by the instance's name attribute.
        """

        self.env_vars.clear()
        for key, value in env.items():
            self.env_vars.append(EnvVar(name=key, value=value, app=self))

    #
    # Actions
    #
    def deploy(self) -> None:
        """Deploys the application by invoking the deployment process.

        This serves as a wrapper that calls the `do_deploy` function,
        which handles the actual deployment steps necessary for the application.
        """
        # Lazy import to avoid circular dependency
        from hop3.deployers import do_deploy  # noqa: PLC0415

        do_deploy(self)

    def destroy(self) -> None:
        """Remove various application-related files and directories, except for
        data.

        This deletes the application directory, repository directory,
        virtual environment, and log files associated with the
        application. It also removes UWSGI and NGINX configuration files
        and sockets. However, it preserves the application's data
        directory.

        For Docker apps, this also removes containers, networks, and volumes.
        """
        app_name = self.name

        # First, clean up runtime resources (Docker containers, etc.)
        if self.runtime == "docker-compose":
            self._destroy_docker_compose()

        def remove_file(p: Path) -> None:
            # Remove the file or directory at the given path if it exists.
            if p.exists():
                if p.is_dir():
                    log(f"Removing directory '{p}'", level=2, fg="blue")
                    shutil.rmtree(p)  # Recursively remove a directory tree
                else:
                    log(f"Removing file '{p}'", level=2, fg="blue")
                    p.unlink()  # Remove a file

        # Leave DATA_ROOT, as apps may create hard-to-reproduce data,
        # and CACHE_ROOT, as `nginx` will set permissions to protect it
        remove_file(self.app_path)
        remove_file(self.repo_path)
        remove_file(self.virtualenv_path)
        remove_file(self.log_path)

        cfg = HopConfig.get_instance()
        for p in [cfg.UWSGI_AVAILABLE, cfg.UWSGI_ENABLED]:
            for f in Path(p).glob(f"{app_name}*.ini"):
                remove_file(f)

        remove_file(cfg.NGINX_ROOT / f"{app_name}.conf")
        remove_file(cfg.NGINX_ROOT / f"{app_name}.sock")
        remove_file(cfg.NGINX_ROOT / f"{app_name}.key")
        remove_file(cfg.NGINX_ROOT / f"{app_name}.crt")

        acme_link = Path(cfg.ACME_WWW, app_name)
        acme_certs = acme_link.resolve()
        remove_file(acme_link)
        remove_file(acme_certs)

        # We preserve data
        data_dir = self.data_path
        if data_dir.exists():
            log(f"Preserving folder '{data_dir}'", level=2, fg="blue")

    def start(self) -> None:
        """Start the application (non-blocking).

        For uWSGI apps: Spawns by writing config files for the uWSGI emperor.
        For Docker apps: Runs docker compose up -d.

        The app transitions to STARTING state. Use sync_state() or check
        app:status to verify when it reaches RUNNING.

        Raises:
            StateTransitionError: If the app is not in a startable state

        Transitions: STOPPED -> STARTING (RUNNING verified by sync_state)
        """
        # Transition to STARTING state
        self._transition_state(AppStateEnum.STARTING)

        try:
            if self.runtime == "docker-compose":
                self._start_docker_compose()
            else:
                # Spawn the application processes (writes config files for uWSGI emperor)
                # This is async - the actual processes start after uWSGI emperor picks up the files
                spawn_app(self)

        except Exception as e:
            # Transition to FAILED state on error
            error_msg = f"Failed to start: {e}"
            self._transition_state(AppStateEnum.FAILED, error_msg)
            log(f"Error starting app '{self.name}': {e}", fg="red")
            raise

    def _start_docker_compose(self) -> None:
        """Start the app using Docker Compose."""
        log(f"Starting Docker Compose app '{self.name}'...", level=2, fg="blue")

        # Use existing port or allocate a new one
        if not self.port or self.port == 0:
            self.port = get_free_port()
            log(f"Allocated port {self.port} for app", level=2)

        # Set up environment with allocated port and image tag
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
            "PORT": str(self.port),
            "HOP3_IMAGE_TAG": self.image_tag or f"hop3/{self.name.lower()}:latest",
            "HOP3_APP_NAME": self.name,
            "HOP3_APP_PORT": str(self.port),
        }

        # Find the compose file (user-supplied or generated)
        compose_file = self._find_compose_file()
        cmd = [
            "docker",
            "compose",
            "-f",
            str(compose_file),
            "-p",
            self.name,
            "up",
            "-d",
            "--remove-orphans",
        ]

        try:
            subprocess.run(
                cmd,
                cwd=self.src_path,
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
            )
            # Transition directly to RUNNING since docker compose up is synchronous
            self._transition_state(AppStateEnum.RUNNING)
            log(f"Docker Compose app '{self.name}' started.", level=2, fg="green")
        except subprocess.CalledProcessError as e:
            log(f"Docker Compose start failed: {e.stderr}", level=2, fg="red")
            raise
        except subprocess.TimeoutExpired:
            log("Docker Compose start timed out", level=2, fg="red")
            raise

    def _find_compose_file(self) -> Path:
        """Find the compose file for this app.

        Returns the path to either:
        1. User-supplied compose file (docker-compose.yml, compose.yml, etc.)
        2. Hop3-generated compose file (.hop3-compose.yml)
        """
        # Check for user-supplied compose files first
        for filename in [
            "docker-compose.yml",
            "docker-compose.yaml",
            "compose.yml",
            "compose.yaml",
        ]:
            compose_path = self.src_path / filename
            if compose_path.exists():
                return compose_path

        # Fall back to Hop3-generated compose file
        generated_path = self.src_path / ".hop3-compose.yml"
        if generated_path.exists():
            return generated_path

        # If no compose file exists, return the generated path anyway
        # (docker compose will fail with a clear error message)
        return generated_path

    def stop(self) -> None:
        """Stop the application (non-blocking).

        For uWSGI apps: Removes config files, emperor stops the vassal.
        For Docker apps: Runs docker compose stop.

        The app transitions to STOPPING state. Use sync_state() or check
        app:status to verify when it reaches STOPPED.

        Always performs cleanup even if state says STOPPED, to handle
        state-reality mismatches.

        Transitions: RUNNING -> STOPPING (STOPPED verified by sync_state)
        """
        # If already stopped, nothing more to do
        if self.run_state == AppStateEnum.STOPPED:
            return

        if self.runtime == "docker-compose":
            self._stop_docker_compose()
        else:
            self._stop_uwsgi()

    def _stop_uwsgi(self) -> None:
        """Stop uWSGI-based app by removing config files."""
        cfg = HopConfig.get_instance()

        # Remove uWSGI config files - emperor will stop the vassal
        config_files = list(cfg.UWSGI_ENABLED.glob(f"{self.name}*.ini"))
        for config_file in config_files:
            config_file.unlink()

        # Transition to STOPPING if coming from RUNNING
        if self.run_state == AppStateEnum.RUNNING:
            self._transition_state(AppStateEnum.STOPPING)
        elif self.run_state == AppStateEnum.STOPPING:
            pass  # Already in STOPPING
        else:
            # For other states (STARTING, FAILED), force to STOPPED directly
            self.run_state = AppStateEnum.STOPPED

    def _stop_docker_compose(self) -> None:
        """Stop Docker Compose app."""
        log(f"Stopping Docker Compose app '{self.name}'...", level=2, fg="blue")

        # Transition to STOPPING if coming from RUNNING
        if self.run_state == AppStateEnum.RUNNING:
            self._transition_state(AppStateEnum.STOPPING)

        # Find the compose file
        compose_file = self._find_compose_file()

        try:
            subprocess.run(
                ["docker", "compose", "-f", str(compose_file), "-p", self.name, "stop"],
                cwd=self.src_path,
                check=False,  # Don't fail if already stopped
                capture_output=True,
                text=True,
                timeout=60,
            )
            # Transition directly to STOPPED since docker compose stop is synchronous
            self._transition_state(AppStateEnum.STOPPED)
            log(f"Docker Compose app '{self.name}' stopped.", level=2, fg="green")
        except subprocess.TimeoutExpired:
            log("Docker Compose stop timed out", level=2, fg="yellow")
            # Force to STOPPED anyway
            self.run_state = AppStateEnum.STOPPED
        except Exception as e:
            log(f"Error stopping Docker Compose app: {e}", level=2, fg="yellow")
            # Force to STOPPED anyway
            self.run_state = AppStateEnum.STOPPED

    def _destroy_docker_compose(self) -> None:
        """Destroy Docker Compose app - remove containers, networks, and volumes."""
        log(f"Destroying Docker Compose app '{self.name}'...", level=2, fg="yellow")

        try:
            # Use 'down --volumes --remove-orphans' to fully clean up
            result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-p",
                    self.name,
                    "down",
                    "--volumes",
                    "--remove-orphans",
                ],
                cwd=self.src_path if self.src_path.exists() else None,
                check=False,  # Don't fail if containers don't exist
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                log(f"Docker Compose app '{self.name}' destroyed.", level=2, fg="green")
            else:
                log(
                    f"Docker Compose down returned {result.returncode}: {result.stderr}",
                    level=2,
                    fg="yellow",
                )
        except subprocess.TimeoutExpired:
            log("Docker Compose destroy timed out", level=2, fg="yellow")
        except Exception as e:
            log(f"Error destroying Docker Compose app: {e}", level=2, fg="yellow")

    def restart(self) -> None:
        """Restart (or just start) a deployed app (non-blocking).

        For uWSGI RUNNING apps: uses touch-based restart (emperor reloads vassal)
        For Docker RUNNING apps: uses docker compose restart
        For STOPPED/FAILED apps: transitions through STARTING
        For STARTING/STOPPING apps: no-op (already in transition)

        Use sync_state() or app:status to verify the app reaches RUNNING.
        """
        log(f"Restarting app '{self.name}'...", fg="blue")

        # If app is already in a transitional state, do nothing
        if self.run_state in {AppStateEnum.STARTING, AppStateEnum.STOPPING}:
            log(
                f"App '{self.name}' is already in {self.run_state.name} state, "
                "skipping restart",
                fg="yellow",
            )
            return

        # If app is running, use runtime-appropriate restart
        if self.run_state == AppStateEnum.RUNNING:
            if self.runtime == "docker-compose":
                self._restart_docker_compose()
            else:
                self._restart_uwsgi()
            return

        # If app is in FAILED state, transition to STOPPED first (recovery)
        if self.run_state == AppStateEnum.FAILED:
            self._transition_state(AppStateEnum.STOPPED)

        # Now start the app (only if we're in STOPPED state)
        if self.run_state == AppStateEnum.STOPPED:
            self.start()

    def _restart_uwsgi(self) -> None:
        """Restart uWSGI app using touch-based restart."""
        cfg = HopConfig.get_instance()
        config_files = list(cfg.UWSGI_ENABLED.glob(f"{self.name}*.ini"))
        if config_files:
            for config_file in config_files:
                config_file.touch()
            log(f"App '{self.name}' restart triggered.", level=2, fg="green")
        else:
            # No config files but state says running - inconsistent state
            log(
                f"App '{self.name}' has no config files, starting fresh.",
                level=2,
                fg="yellow",
            )
            self.run_state = AppStateEnum.STOPPED
            self.start()

    def _restart_docker_compose(self) -> None:
        """Restart Docker Compose app."""
        log(f"Restarting Docker Compose app '{self.name}'...", level=2, fg="blue")

        # Build environment with image tag for compose file substitution
        # This fixes the "HOP3_IMAGE_TAG not set" issue during restart
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
            "PORT": str(self.port) if self.port else "8080",
            "HOP3_IMAGE_TAG": self.image_tag or f"hop3/{self.name.lower()}:latest",
            "HOP3_APP_NAME": self.name,
            "HOP3_APP_PORT": str(self.port) if self.port else "8080",
        }

        try:
            subprocess.run(
                ["docker", "compose", "-p", self.name, "restart"],
                cwd=self.src_path,
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
            )
            log(f"Docker Compose app '{self.name}' restarted.", level=2, fg="green")
        except subprocess.CalledProcessError as e:
            log(f"Docker Compose restart failed: {e.stderr}", level=2, fg="yellow")
            # Fall back to stop/start
            log("Falling back to stop/start...", level=2, fg="yellow")
            self.stop()
            self.start()
        except subprocess.TimeoutExpired:
            log(
                "Docker Compose restart timed out, trying stop/start...",
                level=2,
                fg="yellow",
            )
            self.stop()
            self.start()

    def get_logs(self, lines: int = 100, since: str | None = None) -> list[str]:
        """Get the most recent log lines for the application.

        Args:
            lines: Number of log lines to retrieve (default: 100)
            since: Only return logs after this timestamp (ISO format)

        Returns:
            List of log lines
        """
        # For Docker Compose apps, fetch logs from Docker
        if self.runtime == "docker-compose":
            return self._get_docker_logs(lines, since=since)

        # For other runtimes, read from log files
        return self._get_file_logs(lines, since=since)

    def _get_docker_logs(self, lines: int = 100, since: str | None = None) -> list[str]:
        """Get logs from Docker container(s) for this app.

        Args:
            lines: Number of log lines to retrieve
            since: Only return logs after this timestamp (ISO format)

        Returns:
            List of log lines
        """
        all_logs = []

        try:
            # Use docker compose logs to get logs from all containers
            compose_file = self.src_path / ".hop3-compose.yml"
            if compose_file.exists():
                cmd = [
                    "docker",
                    "compose",
                    "-f",
                    str(compose_file),
                    "-p",
                    self.name,
                    "logs",
                    "--tail",
                    str(lines),
                    "--no-color",
                ]
                # Add --since filter if specified
                if since:
                    cmd.extend(["--since", since])
            else:
                # Fall back to docker logs for the main container
                cmd = [
                    "docker",
                    "logs",
                    "--tail",
                    str(lines),
                    f"{self.name}-web-1",
                ]
                # Add --since filter if specified (docker logs also supports it)
                if since:
                    cmd.insert(-1, "--since")
                    cmd.insert(-1, since)

            result = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.stdout:
                all_logs.append(f"==> docker logs ({self.name}) <==")
                all_logs.extend(result.stdout.strip().split("\n"))

            if result.stderr:
                # Docker compose logs often output to stderr
                if not result.stdout:
                    all_logs.append(f"==> docker logs ({self.name}) <==")
                all_logs.extend(result.stderr.strip().split("\n"))

            if not all_logs:
                all_logs.append(f"No Docker logs found for app '{self.name}'")

        except subprocess.TimeoutExpired:
            all_logs.append(f"Timeout getting Docker logs for app '{self.name}'")
        except FileNotFoundError:
            all_logs.append("Docker command not found. Is Docker installed?")
        except Exception as e:
            all_logs.append(f"Error getting Docker logs: {e}")

        return all_logs

    def _get_file_logs(self, lines: int = 100, since: str | None = None) -> list[str]:
        """Get logs from log files for this app.

        Args:
            lines: Number of log lines to retrieve
            since: Only return logs after this timestamp (ISO format)

        Returns:
            List of log lines
        """
        # Find all log files in the log directory (e.g., web.1.log, worker.1.log)
        if not self.log_path.exists():
            return [f"No log directory found for app '{self.name}'"]

        log_files = sorted(self.log_path.glob("*.log"))
        if not log_files:
            return [f"No log files found for app '{self.name}'"]

        # Parse the 'since' timestamp if provided
        since_dt: datetime | None = None
        if since:
            try:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            except ValueError:
                pass  # Invalid timestamp, ignore filter

        # Collect logs from all workers
        all_logs = []
        for log_file in log_files:
            file_logs = self._read_single_log_file(log_file, since_dt)
            all_logs.extend(file_logs)

        # Return the last N lines across all log files
        return (
            all_logs[-lines:] if all_logs else [f"No log content for app '{self.name}'"]
        )

    def _read_single_log_file(
        self, log_file: Path, since_dt: datetime | None
    ) -> list[str]:
        """Read a single log file and optionally filter by timestamp.

        Args:
            log_file: Path to the log file
            since_dt: Only include lines after this timestamp (or None for all)

        Returns:
            List of log lines from this file
        """
        result = []
        try:
            with Path(log_file).open() as f:
                file_lines = f.readlines()

            # Add header to identify which worker the logs are from
            worker_name = log_file.stem  # e.g., "web.1"
            result.append(f"==> {worker_name} <==")

            for line in file_lines:
                stripped = line.rstrip()
                # Filter by timestamp if since_dt is set
                if since_dt and stripped:
                    line_ts = self._extract_timestamp_from_log(stripped)
                    if line_ts and line_ts < since_dt:
                        continue
                result.append(stripped)
            result.append("")  # Blank line between files
        except Exception as e:
            result.append(f"Error reading {log_file.name}: {e}")

        return result

    def _extract_timestamp_from_log(self, line: str) -> datetime | None:
        """Try to extract a timestamp from the beginning of a log line.

        Supports common log formats:
        - ISO format: 2025-01-15T10:30:00Z
        - Common log format: [15/Jan/2025:10:30:00 +0000]
        - Simple datetime: 2025-01-15 10:30:00

        Args:
            line: A log line

        Returns:
            Parsed datetime or None if no timestamp found
        """
        # Try ISO format first (most common in structured logs)
        iso_match = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", line)
        if iso_match:
            try:
                return datetime.fromisoformat(iso_match.group(1))
            except ValueError:
                pass

        # Try simple datetime format
        simple_match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
        if simple_match:
            try:
                return datetime.fromisoformat(simple_match.group(1))
            except ValueError:
                pass

        return None
