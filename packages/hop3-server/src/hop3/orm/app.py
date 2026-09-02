# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
import time
from contextlib import suppress
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
from hop3.lib import Abort, log, robust_rmtree
from hop3.run.spawn import spawn_app, verify_nix_closure
from hop3.run.uwsgi.naming import vassal_glob

# Imported lazily inside the methods that need it: docker_runtime imports this
# module for App/AppStateEnum, so a module-level import here would be a cycle.
# The docker work lives there because 477 lines of subprocess orchestration do
# not belong in a persistence class — see that module's docstring.

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.engine.interfaces import Dialect

    from .addon_credential import AddonCredential
    from .app_admin_credential import AppAdminCredential
    from .env import EnvVar
    from .port_claim import PortClaim


class AppStateEnum(Enum):
    """
    Enumeration for representing the state of an application.

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

    def __init__(self, enum_class: type[Enum]) -> None:
        self.enum_class = enum_class
        super().__init__()

    def process_bind_param(self, value: object, dialect: Dialect) -> int | None:
        """Convert enum to integer for storage."""
        if value is None:
            return None
        if isinstance(value, self.enum_class):
            return value.value
        # A value already in storage form (e.g. a raw int bound via a literal
        # query); an Integer column only ever binds an int here.
        if isinstance(value, int):
            return value
        msg = (
            f"{type(self).__name__} can't bind {value!r}: "
            f"expected {self.enum_class.__name__} or int"
        )
        raise TypeError(msg)

    def process_result_value(self, value: object, dialect: Dialect) -> Enum | None:
        """Convert integer to enum when reading."""
        if value is None:
            return None
        # Handle both string and integer values from database
        # SQLite may return strings, so convert to int first
        if isinstance(value, str):
            value = int(value)
        # Through a plain callable: calling a `type[Enum]` is otherwise read as
        # the functional `Enum("Name", ...)` API by mypy-style checkers.
        to_enum: Callable[[object], Enum] = self.enum_class
        return to_enum(value)


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
    """
    Represents an application with relevant properties such as name, run
    state, and port.
    """

    __tablename__ = "app"

    # Unique: the app name is the identity for every lookup *and* the
    # on-disk path (APP_ROOT / name). Without the constraint two rows can
    # share a name, after which every get_app_or_none() raises
    # MultipleResultsFound and the app is unreachable from CLI and dashboard
    # alike — the row is insertable, so nothing stops it happening.
    name: Mapped[str] = mapped_column(String(128), unique=True)
    runtime: Mapped[str] = mapped_column(String(64), default="uwsgi")
    run_state: Mapped[AppStateEnum] = mapped_column(
        IntEnum(AppStateEnum), default=AppStateEnum.STOPPED
    )
    port: Mapped[int] = mapped_column(default=0)
    # L7 WAF (ADR 050): loopback port of the per-app LeWAF proxy that fronts the
    # app's web socket when [waf].enabled. 0 = no WAF proxy. When set, nginx
    # points here instead of `port`, and the proxy upstreams to `port`.
    waf_port: Mapped[int] = mapped_column(default=0)
    hostname: Mapped[str] = mapped_column(default="")
    error_message: Mapped[str] = mapped_column(String(1024), default="")
    state_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=None, nullable=True
    )
    # Image tag for container-based runtimes (e.g., "hop3/myapp:latest")
    # Not nullable: the annotation says `str` and the code reads it as one
    # (`self.image_tag or ...`). nullable=True let the DB hand back None where
    # the type promised a string.
    image_tag: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    # Timestamp of last successful deployment (for --since-deploy log filter)
    last_deployed_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=None, nullable=True
    )
    # Resolved [limits] enforcement outcome (ADR 046 §3 / P2.2), surfaced by
    # `hop3 app status`: "" (none) | "cgroup" | "docker" | "unenforced".
    # limits_detail carries the applied caps, or the why-unenforced reason.
    limits_enforced: Mapped[str] = mapped_column(String(16), default="")
    limits_detail: Mapped[str] = mapped_column(String(512), default="")

    env_vars: Mapped[list[EnvVar]] = relationship(
        back_populates="app", cascade="all, delete-orphan", lazy="selectin"
    )

    addon_credentials: Mapped[list[AddonCredential]] = relationship(
        back_populates="app", cascade="all, delete-orphan", lazy="selectin"
    )

    admin_credential: Mapped[AppAdminCredential | None] = relationship(
        back_populates="app",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin",
    )

    port_claims: Mapped[list[PortClaim]] = relationship(
        back_populates="app", cascade="all, delete-orphan", lazy="selectin"
    )

    def check_exists(self) -> None:
        if not (HopConfig.get_instance().APP_ROOT / self.name).exists():
            msg = f"Error: app '{self.name}' not found."
            raise Abort(msg)

    def create(self, setup_git: bool = False) -> None:
        """
        Create app directories and optionally set up git repository.

        Args:
            setup_git: If True, also initialize a bare git repository with
                      post-receive hook for git push deployment.
        """
        self.app_path.mkdir(exist_ok=True)
        # The data directory may already exist, since this may be
        # a full redeployment
        # (we never delete data since it may be expensive to recreate)
        for path in [self.repo_path, self.src_path, self.data_path, self.log_path]:
            path.mkdir(exist_ok=True)

        if setup_git:
            from hop3.core.git import (  # ruff:ignore[import-outside-top-level]
                GitManager,
            )

            GitManager(app=self).setup_hook()

    @property
    def is_running(self) -> bool:
        """Check if app reports as RUNNING in database state."""
        return self.run_state == AppStateEnum.RUNNING

    def check_actual_status(self) -> AppStateEnum:
        """
        Check the actual running status by delegating to the deployment strategy.

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
        """
        Synchronize database state with actual running status.

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
                self.transition_state(AppStateEnum.RUNNING)
                return True
        elif current_state == AppStateEnum.STOPPING:
            if actual_status == AppStateEnum.STOPPED:
                self.transition_state(AppStateEnum.STOPPED)
                return True

        return False

    def wait_for_actual_state(
        self,
        expected_state: AppStateEnum,
        timeout: float = 10.0,
        poll_interval: float = 0.5,
    ) -> bool:
        """
        Wait for the app to reach the expected actual state.

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

    def transition_state(self, new_state: AppStateEnum, error_msg: str = "") -> None:
        """
        Transition to a new state with validation.

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
        """
        Path to the root directory of the app.

        Defense-in-depth: reject names that would escape APP_ROOT even if
        validation at the RPC boundary is ever bypassed. The primary check
        is ``hop3.core.identifiers.validate_app_name`` at command entry;
        this guard catches anything that slips past.
        """
        name = self.name
        parts = Path(name).parts
        if (
            ".." in parts
            or "/" in name
            or "\\" in name
            or name.startswith(".")
            or not name
        ):
            msg = f"Unsafe app name {name!r}: refusing to resolve path."
            raise ValueError(msg)
        return HopConfig.get_instance().APP_ROOT / name

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
    def volumes_path(self) -> Path:
        """
        Root of the app's persistent volumes (ADR 046 §2).

        Each declared ``[[volumes]]`` entry stores its data under
        ``volumes_path / <name>`` — outside ``src/`` so it survives the
        source-replacing redeploy.
        """
        return self.app_path / "volumes"

    @property
    def log_path(self) -> Path:
        """Path to the log directory of the app."""
        return self.app_path / "log"

    @property
    def virtualenv_path(self) -> Path:
        """Pathe to the virtualenv of the app."""
        return self.app_path / "venv"

    def get_runtime_env(self) -> Env:
        """
        Retrieves the runtime environment for the current application.

        This fetches the environment settings for the application
        identified by the instance's name attribute.
        """
        data = {}
        for env_var in self.env_vars:
            data[env_var.name] = env_var.value
        return Env(data)

    def update_runtime_env(self, env: Env) -> None:
        """
        Updates the runtime environment for the current application.

        This updates the environment settings for the application
        identified by the instance's name attribute.
        """
        # EnvVar is imported under TYPE_CHECKING to avoid a circular import with
        # .env; import it locally here where it is actually instantiated.
        from .env import EnvVar  # ruff:ignore[import-outside-top-level]

        self.env_vars.clear()
        for key, value in env.items():
            self.env_vars.append(EnvVar(name=key, value=value, app=self))

    #
    # Actions
    #
    def deploy(self) -> None:
        """
        Deploys the application by invoking the deployment process.

        This serves as a wrapper that calls the `do_deploy` function,
        which handles the actual deployment steps necessary for the application.
        """
        # Lazy import to avoid circular dependency
        from hop3.deployers import do_deploy  # ruff:ignore[import-outside-top-level]

        do_deploy(self)

    def destroy(self) -> None:
        """
        Completely remove the application and all of its data.

        This is a full teardown (per the platform rule that destroy must leave
        no leftover process, port, config, or disk): it removes the application
        directory — including the data directory and any persistent
        ``volumes/`` — plus the bare repository, virtualenv, logs, and the
        uWSGI / NGINX / ACME configuration and sockets. The global DATA_ROOT and
        CACHE_ROOT are left untouched (they are not app-specific).

        Persistent data is removed too, so this loudly warns about non-empty
        data/volume directories before deleting them — back up first with
        ``hop3 backup create`` if you need them.

        For Docker apps, this also removes containers, networks, and volumes.
        """
        from hop3.deployers import (  # ruff:ignore[import-outside-top-level]
            docker_runtime,
        )

        app_name = self.name

        # Reap leftover app processes FIRST, regardless of recorded state: a
        # daemon that exec'd into a Nix-store path can survive a prior (false)
        # STOPPED and keep holding a fixed port. Removing its files — or the DB
        # row — while it runs would strand both the process and the port. Docker
        # runtimes are torn down by _destroy_docker_compose below.
        if self.runtime != "docker-compose":
            from hop3.run.reaper import (  # ruff:ignore[import-outside-top-level]
                reap_app_processes,
            )

            survivors = reap_app_processes(app_name)
            if survivors:
                msg = (
                    f"{len(survivors)} process(es) for '{app_name}' survived SIGKILL "
                    f"(pids {survivors}) and still hold their ports"
                )
                raise RuntimeError(msg)

        # Drop any native [limits] cgroup leaf (ADR 046 §3) for ALL runtimes: an
        # app deployed native (with a leaf) then redeployed to Docker would still
        # have a stale leaf this is the only place that reclaims. Processes are
        # already reaped (native, above) or torn down (Docker, below), so the leaf
        # is empty. Idempotent + best-effort (absent leaf is a no-op).
        from hop3.deployers.native_limits import (  # ruff:ignore[import-outside-top-level]
            remove_native_limits,
        )

        remove_native_limits(app_name)

        # First, clean up runtime resources (Docker containers, etc.)
        if self.runtime == "docker-compose":
            docker_runtime.destroy_docker_compose(self)
        else:
            # Even if runtime isn't docker-compose, try to clean up any orphan
            # Docker resources that might exist for this app name
            docker_runtime.cleanup_orphan_docker_resources(self)

        def remove_file(p: Path) -> None:
            # Remove the file or directory at the given path if it exists.
            if p.exists():
                if p.is_dir():
                    log(f"Removing directory '{p}'", level=2, fg="blue")
                    # Use robust removal for directories - handles read-only files
                    # (common in site-packages, node_modules) and race conditions
                    robust_rmtree(p)
                else:
                    log(f"Removing file '{p}'", level=2, fg="blue")
                    p.unlink()  # Remove a file

        # Persistent data (data/ and any volumes/) lives under app_path and is
        # removed with it. That is intentional — a full teardown must leave no
        # leftover disk — but it is permanent, so warn loudly first rather than
        # deleting it silently. (The global DATA_ROOT / CACHE_ROOT are separate
        # and are not touched here.)
        for label, path in [
            ("data", self.data_path),
            ("volumes", self.volumes_path),
        ]:
            if path.exists() and any(path.iterdir()):
                log(
                    f"  Removing {label} for '{app_name}' permanently "
                    f"(back it up first with 'hop3 backup create'): {path}",
                    level=0,
                    fg="yellow",
                )

        remove_file(self.app_path)
        remove_file(self.repo_path)
        remove_file(self.virtualenv_path)
        remove_file(self.log_path)

        cfg = HopConfig.get_instance()
        for p in [cfg.UWSGI_AVAILABLE, cfg.UWSGI_ENABLED]:
            for f in Path(p).glob(vassal_glob(app_name)):
                remove_file(f)

        remove_file(cfg.NGINX_ROOT / f"{app_name}.conf")
        remove_file(cfg.NGINX_ROOT / f"{app_name}.sock")
        remove_file(cfg.NGINX_ROOT / f"{app_name}.key")
        remove_file(cfg.NGINX_ROOT / f"{app_name}.crt")

        acme_link = Path(cfg.ACME_WWW, app_name)
        acme_certs = acme_link.resolve()
        remove_file(acme_link)
        remove_file(acme_certs)

    def start(self) -> None:
        """
        Start the application (non-blocking).

        For uWSGI apps: Spawns by writing config files for the uWSGI emperor.
        For Docker apps: Runs docker compose up -d.

        The app transitions to STARTING state. Use sync_state() or check
        app status to verify when it reaches RUNNING.

        Raises:
            StateTransitionError: If the app is not in a startable state

        Transitions: STOPPED -> STARTING (RUNNING verified by sync_state)
        """
        from hop3.deployers import (  # ruff:ignore[import-outside-top-level]
            docker_runtime,
        )

        # An app that never deployed successfully has no artifact to run: its
        # venv/image is absent or half-built, so spawning it can only produce a
        # doomed process and a generic "failed to start within 60s" — burying
        # the real cause (e.g. "unpinned requirements") that the build already
        # reported. Refuse, and point at the build log.
        if self.last_deployed_at is None:
            msg = (
                f"App '{self.name}' can't start: it has never deployed "
                f"successfully, so there is nothing built to run. Check the "
                f"build failure with `hop3 app build-logs --app {self.name}`, "
                f"fix it, then `hop3 deploy`."
            )
            raise StateTransitionError(msg)

        # Transition to STARTING state
        self.transition_state(AppStateEnum.STARTING)

        try:
            if self.runtime == "docker-compose":
                docker_runtime.start_docker_compose(self)
            else:
                # Spawn the application processes (writes config files for uWSGI emperor)
                # This is async - the actual processes start after uWSGI emperor picks up the files
                spawn_app(self)

        except Exception as e:
            # Transition to FAILED state on error
            error_msg = f"Failed to start: {e}"
            self.transition_state(AppStateEnum.FAILED, error_msg)
            log(f"Error starting app '{self.name}': {e}", fg="red")
            raise

    def stop(self) -> None:
        """
        Stop the application (non-blocking).

        For uWSGI apps: Removes config files, emperor stops the vassal.
        For Docker apps: Runs docker compose stop.

        Reaps and verifies: the app's processes/containers (and the ports they
        hold) must be confirmed gone before STOPPED is reported — see
        _stop_uwsgi / _stop_docker_compose. Raises if anything survives even
        SIGKILL, so a freed PortClaim can never outlive a still-bound port.

        Skips work when already recorded STOPPED. Callers that need cleanup
        regardless of recorded state (destroy) reap independently — a recorded
        STOPPED can be false for a daemon that exec'd into a Nix-store path.
        """
        from hop3.deployers import (  # ruff:ignore[import-outside-top-level]
            docker_runtime,
        )

        # If already stopped, nothing more to do (destroy() reaps independently).
        if self.run_state == AppStateEnum.STOPPED:
            return

        if self.runtime == "docker-compose":
            docker_runtime.stop_docker_compose(self)
        else:
            self._stop_uwsgi()

    def _stop_uwsgi(self) -> None:
        """
        Stop a uWSGI app: remove the Emperor config, then CONFIRM the
        processes are actually gone before reporting STOPPED.

        Removing the ``.ini`` makes the Emperor stop the vassal, but a daemon
        that ``exec``'d into a Nix-store path (e.g. owncast) can ignore that and
        keep holding a fixed port. We reap-and-verify (force-killing stragglers)
        so STOPPED is truthful — otherwise a freed PortClaim lets the next deploy
        of that port fail at runtime with 'address already in use'.
        """
        from hop3.run.reaper import (  # ruff:ignore[import-outside-top-level]
            reap_app_processes,
        )

        cfg = HopConfig.get_instance()

        # Remove uWSGI config files - emperor will stop the vassal
        for config_file in cfg.UWSGI_ENABLED.glob(vassal_glob(self.name)):
            config_file.unlink()

        if self.run_state == AppStateEnum.RUNNING:
            self.transition_state(AppStateEnum.STOPPING)

        # Confirm the processes are gone — don't trust that the Emperor reaped
        # them (it doesn't, for an exec'd daemon that ignores SIGTERM).
        survivors = reap_app_processes(self.name)
        if survivors:
            msg = (
                f"Could not stop all processes for '{self.name}': {len(survivors)} "
                f"still running (pids {survivors}) and may still hold their ports."
            )
            raise RuntimeError(msg)
        self.mark_stopped()

    def mark_stopped(self) -> None:
        """
        Record a confirmed-STOPPED state with fresh metadata.

        Bypasses ``transition_state`` on purpose: the entry state may be one the
        state machine forbids → STOPPED (e.g. STARTING/FAILED), but reaping has
        confirmed the processes are gone, so STOPPED is the truth. We still
        refresh ``state_changed_at`` and clear any stale ``error_message`` so a
        cleanly-stopped app doesn't carry a leftover failure message.
        """
        self.run_state = AppStateEnum.STOPPED
        self.state_changed_at = datetime.now(UTC)
        self.error_message = ""

    def restart(self) -> None:
        """
        Restart (or just start) a deployed app (non-blocking).

        For uWSGI RUNNING apps: uses touch-based restart (emperor reloads vassal)
        For Docker RUNNING apps: uses docker compose restart
        For STOPPED/FAILED apps: transitions through STARTING
        For STARTING/STOPPING apps: no-op (already in transition)

        Use sync_state() or app status to verify the app reaches RUNNING.
        """
        from hop3.deployers import (  # ruff:ignore[import-outside-top-level]
            docker_runtime,
        )

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
                docker_runtime.restart_docker_compose(self)
            else:
                self._restart_uwsgi()
            return

        # If app is in FAILED state, transition to STOPPED first (recovery)
        if self.run_state == AppStateEnum.FAILED:
            self.transition_state(AppStateEnum.STOPPED)

        # Now start the app (only if we're in STOPPED state)
        if self.run_state == AppStateEnum.STOPPED:
            self.start()

    def _restart_uwsgi(self) -> None:
        """Restart uWSGI app using touch-based restart."""
        # A touch-restart relaunches the vassal from its existing .ini, so it
        # never reaches spawn_app — and therefore never reached the closure
        # guard. That left the guard blind on the one path where a reclaimed
        # Nix closure actually bites: collect garbage, restart, exec a store
        # path that is gone, wait out the health-check timeout.
        verify_nix_closure(self)

        cfg = HopConfig.get_instance()
        config_files = list(cfg.UWSGI_ENABLED.glob(vassal_glob(self.name)))
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

    def get_logs(self, lines: int = 100, since: str | None = None) -> list[str]:
        """
        Get the most recent log lines for the application.

        Args:
            lines: Number of log lines to retrieve (default: 100)
            since: Only return logs after this timestamp (ISO format)

        Returns:
            List of log lines
        """
        from hop3.deployers import (  # ruff:ignore[import-outside-top-level]
            docker_runtime,
        )

        # For Docker Compose apps, fetch logs from Docker
        if self.runtime == "docker-compose":
            return docker_runtime.get_docker_logs(self, lines, since=since)

        # For other runtimes, read from log files
        return self._get_file_logs(lines, since=since)

    def _get_file_logs(self, lines: int = 100, since: str | None = None) -> list[str]:
        """
        Get logs from log files for this app.

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
            # Invalid timestamp, ignore filter
            with suppress(ValueError):
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))

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
        """
        Read a single log file and optionally filter by timestamp.

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
        """
        Try to extract a timestamp from the beginning of a log line.

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
