# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
import re
import subprocess
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
from hop3.lib import Abort, get_free_port, log, robust_rmtree
from hop3.run.spawn import spawn_app, verify_nix_closure

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

    name: Mapped[str] = mapped_column(String(128))
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
    image_tag: Mapped[str] = mapped_column(String(256), default="", nullable=True)
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

    def _transition_state(self, new_state: AppStateEnum, error_msg: str = "") -> None:
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
            self._destroy_docker_compose()
        else:
            # Even if runtime isn't docker-compose, try to clean up any orphan
            # Docker resources that might exist for this app name
            self._cleanup_orphan_docker_resources()

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
        """
        Find the compose file for this app.

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
        # If already stopped, nothing more to do (destroy() reaps independently).
        if self.run_state == AppStateEnum.STOPPED:
            return

        if self.runtime == "docker-compose":
            self._stop_docker_compose()
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
        for config_file in cfg.UWSGI_ENABLED.glob(f"{self.name}*.ini"):
            config_file.unlink()

        if self.run_state == AppStateEnum.RUNNING:
            self._transition_state(AppStateEnum.STOPPING)

        # Confirm the processes are gone — don't trust that the Emperor reaped
        # them (it doesn't, for an exec'd daemon that ignores SIGTERM).
        survivors = reap_app_processes(self.name)
        if survivors:
            msg = (
                f"Could not stop all processes for '{self.name}': {len(survivors)} "
                f"still running (pids {survivors}) and may still hold their ports."
            )
            raise RuntimeError(msg)
        self._mark_stopped()

    def _mark_stopped(self) -> None:
        """
        Record a confirmed-STOPPED state with fresh metadata.

        Bypasses ``_transition_state`` on purpose: the entry state may be one the
        state machine forbids → STOPPED (e.g. STARTING/FAILED), but reaping has
        confirmed the processes are gone, so STOPPED is the truth. We still
        refresh ``state_changed_at`` and clear any stale ``error_message`` so a
        cleanly-stopped app doesn't carry a leftover failure message.
        """
        self.run_state = AppStateEnum.STOPPED
        self.state_changed_at = datetime.now(UTC)
        self.error_message = ""

    def _stop_docker_compose(self) -> None:
        """Stop Docker Compose app."""
        log(f"Stopping Docker Compose app '{self.name}'...", level=2, fg="blue")

        # Transition to STOPPING if coming from RUNNING
        if self.run_state == AppStateEnum.RUNNING:
            self._transition_state(AppStateEnum.STOPPING)

        # Find the compose file
        compose_file = self._find_compose_file()

        # Build environment with image tag for compose file substitution
        # This fixes the "HOP3_IMAGE_TAG not set" issue during stop
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
            "PORT": str(self.port) if self.port else "8080",
            "HOP3_IMAGE_TAG": self.image_tag or f"hop3/{self.name.lower()}:latest",
            "HOP3_APP_NAME": self.name,
        }

        try:
            result = subprocess.run(
                ["docker", "compose", "-f", str(compose_file), "-p", self.name, "stop"],
                cwd=self.src_path,
                env=env,
                check=False,  # Don't fail if already stopped
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                log(
                    f"Docker Compose stop warning: {result.stderr}",
                    level=2,
                    fg="yellow",
                )
        except subprocess.TimeoutExpired:
            log(
                "Docker Compose stop timed out; verifying/force-killing",
                level=2,
                fg="yellow",
            )
        except Exception as e:
            log(
                f"Error stopping Docker Compose app: {e}; verifying",
                level=2,
                fg="yellow",
            )

        # Verify the containers are actually down; force-kill any survivor so its
        # published port is released, then confirm before reporting STOPPED — a
        # slow/failed 'compose stop' must NOT be reported as a clean STOPPED.
        running = self._app_container_ids(running_only=True)
        if running:
            log(
                f"Force-killing {len(running)} container(s) still running for "
                f"'{self.name}'",
                level=2,
                fg="yellow",
            )
            with suppress(Exception):
                subprocess.run(
                    ["docker", "kill", *running],
                    capture_output=True,
                    check=False,
                    timeout=30,
                )
            running = self._app_container_ids(running_only=True)
        if running:
            msg = (
                f"Docker app '{self.name}' has {len(running)} container(s) still "
                f"running after stop+kill; they still hold their ports."
            )
            raise RuntimeError(msg)
        self._mark_stopped()
        log(f"Docker Compose app '{self.name}' stopped.", level=2, fg="green")

    def _destroy_docker_compose(self) -> None:
        """Destroy Docker Compose app - remove containers, networks, and volumes."""
        log(f"Destroying Docker Compose app '{self.name}'...", level=2, fg="yellow")

        # Build the docker compose command
        # Include -f to specify compose file if it exists, otherwise Docker Compose
        # won't know which networks/volumes to clean up
        compose_file = self.src_path / ".hop3-compose.yml"
        cmd = ["docker", "compose"]

        if compose_file.exists():
            cmd.extend(["-f", str(compose_file)])

        # `--rmi all` removes the per-app image (hop3/<app>:latest) too.
        # Without it, every deploy leaks a 0.5-1.5 GB image (the app name is
        # timestamped, so the tag is unique each run and never overwritten),
        # filling the disk fast. Base images are FROM layers, not compose
        # `image:` services, so they are NOT removed by this.
        cmd.extend([
            "-p",
            self.name,
            "down",
            "--rmi",
            "all",
            "--volumes",
            "--remove-orphans",
        ])

        # Build environment with image tag for compose file substitution
        # This fixes the "HOP3_IMAGE_TAG not set" issue during destroy
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
            "PORT": str(self.port) if self.port else "8080",
            "HOP3_IMAGE_TAG": self.image_tag or f"hop3/{self.name.lower()}:latest",
            "HOP3_APP_NAME": self.name,
        }

        try:
            # Use 'down --volumes --remove-orphans' to fully clean up
            result = subprocess.run(
                cmd,
                cwd=self.src_path if self.src_path.exists() else None,
                env=env,
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

        # Safety net: 'down' is best-effort (check=False, may time out). Remove
        # any container it left behind — otherwise it keeps the published host
        # port and collides by name on the next deploy. (The orphan reaper is
        # only on the non-docker branch of destroy(), so do it here too.)
        leftover = self._app_container_ids()
        if leftover:
            log(
                f"Force-removing {len(leftover)} leftover container(s) for "
                f"'{self.name}' after compose down",
                level=2,
                fg="yellow",
            )
            with suppress(Exception):
                subprocess.run(
                    ["docker", "rm", "-f", *leftover],
                    capture_output=True,
                    check=False,
                    timeout=60,
                )

        # Always try to force cleanup the network as a safety measure
        # docker compose down should remove it, but sometimes networks are left behind
        self._force_cleanup_docker_network()

        # Safety net: remove the per-app image directly, in case `down --rmi`
        # missed it (e.g. the compose file was already gone). Base images are
        # never tagged `hop3/...`, so this only drops the app's own image.
        self._force_cleanup_docker_image()

    def _app_container_ids(self, *, running_only: bool = False) -> list[str]:
        """
        IDs of this app's containers, matched by Compose project label.

        ``running_only`` limits to currently-running containers; otherwise it
        includes stopped ones too. The project label is an exact match (unlike a
        container-name substring), so it can't catch a different app by prefix.
        """
        flag = "-q" if running_only else "-aq"
        with suppress(Exception):  # docker missing / timeout -> nothing to report
            result = subprocess.run(
                [
                    "docker",
                    "ps",
                    flag,
                    "--filter",
                    f"label=com.docker.compose.project={self.name}",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().split("\n")
        return []

    def _force_cleanup_docker_image(self) -> None:
        """Force-remove the app's own image; safe no-op if already gone."""
        image_tag = self.image_tag or f"hop3/{self.name.lower()}:latest"
        with suppress(Exception):  # best-effort cleanup
            subprocess.run(
                ["docker", "rmi", "-f", image_tag],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )

    def _force_cleanup_docker_network(self) -> None:
        """Force cleanup of Docker network when compose file is missing."""
        network_name = f"{self.name}_default"
        log(
            f"Attempting to force remove network '{network_name}'...",
            level=2,
            fg="yellow",
        )
        try:
            result = subprocess.run(
                ["docker", "network", "rm", network_name],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            if result.returncode == 0:
                log(f"Removed orphan network '{network_name}'", level=2, fg="green")
            # Don't log error if network doesn't exist - that's fine
        except Exception:
            pass  # Best effort cleanup

    def _cleanup_orphan_docker_resources(self) -> None:
        """
        Clean up any orphan Docker resources for this app.

        This is called when destroying apps that aren't marked as docker-compose
        but might have orphan Docker containers/networks from previous deployments
        or failed cleanups.
        """
        try:
            # Check if any containers exist for this app
            result = subprocess.run(
                ["docker", "ps", "-aq", "--filter", f"name={self.name}-"],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                # Containers exist - stop and remove them
                container_ids = result.stdout.strip().split("\n")
                log(
                    f"Found {len(container_ids)} orphan container(s) for '{self.name}'",
                    level=2,
                    fg="yellow",
                )
                for container_id in container_ids:
                    subprocess.run(
                        ["docker", "rm", "-f", container_id],
                        capture_output=True,
                        check=False,
                        timeout=30,
                    )

            # Try to remove the network
            self._force_cleanup_docker_network()

        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass  # Docker not available or timed out
        except Exception:
            pass  # Best effort cleanup

    def restart(self) -> None:
        """
        Restart (or just start) a deployed app (non-blocking).

        For uWSGI RUNNING apps: uses touch-based restart (emperor reloads vassal)
        For Docker RUNNING apps: uses docker compose restart
        For STOPPED/FAILED apps: transitions through STARTING
        For STARTING/STOPPING apps: no-op (already in transition)

        Use sync_state() or app status to verify the app reaches RUNNING.
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
        # A touch-restart relaunches the vassal from its existing .ini, so it
        # never reaches spawn_app — and therefore never reached the closure
        # guard. That left the guard blind on the one path where a reclaimed
        # Nix closure actually bites: collect garbage, restart, exec a store
        # path that is gone, wait out the health-check timeout.
        verify_nix_closure(self)

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
        """
        Get the most recent log lines for the application.

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
        """
        Get logs from Docker container(s) for this app.

        Args:
            lines: Number of log lines to retrieve
            since: Only return logs after this timestamp (ISO format)

        Returns:
            List of log lines
        """
        all_logs = []

        # Build environment with image tag for compose file substitution
        # This prevents "HOP3_IMAGE_TAG not set" warnings when parsing compose file
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
            "PORT": str(self.port) if self.port else "8080",
            "HOP3_IMAGE_TAG": self.image_tag or f"hop3/{self.name.lower()}:latest",
            "HOP3_APP_NAME": self.name,
        }

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
                env=env,
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
