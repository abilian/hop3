# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import shutil
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from advanced_alchemy.base import BigIntAuditBase
from sqlalchemy import String, TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Integer as SQLInteger

from hop3.config import HopConfig
from hop3.core.env import Env
from hop3.deployers import do_deploy
from hop3.lib import Abort, log
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

    env_vars: Mapped[list[EnvVar]] = relationship(
        back_populates="app", cascade="all, delete-orphan"
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
        from hop3.core.plugins import get_deployer_by_name

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
            msg = f"Invalid state transition: {current_state.name} -> {new_state.name}"
            raise StateTransitionError(msg)

        self.run_state = new_state
        if new_state == AppStateEnum.FAILED:
            self.error_message = error_msg
        else:
            # Clear error message on successful state transitions
            self.error_message = ""

        log(
            f"App '{self.name}' state: {current_state.name} -> {new_state.name}",
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
        do_deploy(self)

    def destroy(self) -> None:
        """Remove various application-related files and directories, except for
        data.

        This deletes the application directory, repository directory,
        virtual environment, and log files associated with the
        application. It also removes UWSGI and NGINX configuration files
        and sockets. However, it preserves the application's data
        directory.
        """
        # TODO: finish refactoring this method
        app_name = self.name

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
        """Start the application with proper state transitions.

        Transitions: STOPPED -> STARTING
        The app stays in STARTING until actual status is verified.
        Use sync_state() to update to RUNNING once processes are confirmed running.

        Raises:
            StateTransitionError: If the app is not in a startable state
        """
        # Transition to STARTING state
        self._transition_state(AppStateEnum.STARTING)

        try:
            # Spawn the application processes (writes config files for uWSGI emperor)
            # This is async - the actual processes start after uWSGI emperor picks up the files
            spawn_app(self)

            # NOTE: We deliberately do NOT transition to RUNNING here
            # The app stays in STARTING state until sync_state() verifies it's actually running

        except Exception as e:
            # Transition to FAILED state on error
            error_msg = f"Failed to start: {e}"
            self._transition_state(AppStateEnum.FAILED, error_msg)
            log(f"Error starting app '{self.name}': {e}", fg="red")
            raise

    def stop(self) -> None:
        """Stop the application with proper state transitions.

        Transitions: RUNNING -> STOPPING
        The app stays in STOPPING until actual status is verified.
        Use sync_state() to update to STOPPED once processes are confirmed stopped.

        Raises:
            StateTransitionError: If the app is not in a stoppable state
        """
        # Transition to STOPPING state
        self._transition_state(AppStateEnum.STOPPING)

        try:
            app_name = self.name
            config_files = list(
                HopConfig.get_instance().UWSGI_ENABLED.glob(f"{app_name}*.ini")
            )

            if len(config_files) > 0:
                log(f"Stopping app '{app_name}'...", fg="blue")
                for config_file in config_files:
                    config_file.unlink()
            else:
                # App not deployed - treat as warning, not error
                log(f"Warning: app '{app_name}' has no running processes", fg="yellow")

            # NOTE: We deliberately do NOT transition to STOPPED here
            # The app stays in STOPPING state until sync_state() verifies it's actually stopped

        except Exception as e:
            # Transition to FAILED state on error
            error_msg = f"Failed to stop: {e}"
            self._transition_state(AppStateEnum.FAILED, error_msg)
            log(f"Error stopping app '{self.name}': {e}", fg="red")
            raise

    def restart(self) -> None:
        """Restart (or just start) a deployed app.

        For RUNNING apps: transitions through STOPPING -> STOPPED -> STARTING -> RUNNING
        For STOPPED/FAILED apps: transitions through STARTING -> RUNNING
        For STARTING/STOPPING apps: no-op (already in transition)

        This method handles the state machine transitions properly.
        """
        log(f"Restarting app '{self.name}'...", fg="blue")

        # If app is already in a transitional state, do nothing
        if self.run_state in (AppStateEnum.STARTING, AppStateEnum.STOPPING):
            log(
                f"App '{self.name}' is already in {self.run_state.name} state, skipping restart",
                fg="yellow",
            )
            return

        # If app is running, stop it first
        if self.run_state == AppStateEnum.RUNNING:
            self.stop()
            # Transition to STOPPED after stopping (completing the STOPPING state)
            self._transition_state(AppStateEnum.STOPPED)

        # If app is in FAILED state, transition to STOPPED first (recovery)
        if self.run_state == AppStateEnum.FAILED:
            self._transition_state(AppStateEnum.STOPPED)

        # Now start the app (only if we're in STOPPED state)
        if self.run_state == AppStateEnum.STOPPED:
            self.start()

    def get_logs(self, lines: int = 100) -> list[str]:
        """Get the most recent log lines for the application.

        Args:
            lines: Number of log lines to retrieve (default: 100)

        Returns:
            List of log lines
        """
        # Find all log files in the log directory (e.g., web.1.log, worker.1.log)
        if not self.log_path.exists():
            return [f"No log directory found for app '{self.name}'"]

        log_files = sorted(self.log_path.glob("*.log"))
        if not log_files:
            return [f"No log files found for app '{self.name}'"]

        # Collect logs from all workers
        all_logs = []
        for log_file in log_files:
            try:
                with open(log_file) as f:
                    file_lines = f.readlines()
                    # Add header to identify which worker the logs are from
                    worker_name = log_file.stem  # e.g., "web.1"
                    all_logs.append(f"==> {worker_name} <==")
                    all_logs.extend(line.rstrip() for line in file_lines)
                    all_logs.append("")  # Blank line between files
            except Exception as e:
                all_logs.append(f"Error reading {log_file.name}: {e}")

        # Return the last N lines across all log files
        return (
            all_logs[-lines:] if all_logs else [f"No log content for app '{self.name}'"]
        )
