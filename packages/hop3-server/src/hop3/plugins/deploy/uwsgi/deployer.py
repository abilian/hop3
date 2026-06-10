# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from hop3.config import UWSGI_ENABLED, HopConfig
from hop3.core.protocols import (
    BuildArtifact,
    DeploymentContext,
    DeploymentInfo,
)
from hop3.lib import log
from hop3.orm import App, AppStateEnum
from hop3.project.procfile import parse_procfile
from hop3.run.spawn import spawn_app

# Grace period after the Emperor stops a vassal before we force-kill leftovers.
_GRACEFUL_STOP_SECONDS = 10.0


def _proc_belongs_to_app(cmdline: str, cwd: str, app_name: str) -> bool:
    """Whether a process (by its cmdline + cwd) belongs to ``app_name``.

    Robust to the two cases plain ``pgrep -f apps/<name>`` gets wrong:

    - A daemon that ``exec``s into a path outside the app dir (a Nix-store
      binary becomes argv ``/nix/store/.../bin/owncast``) — its cmdline no
      longer mentions the app, but its working directory still does.
    - Name-prefix collisions: ``owncast-12`` must not match ``owncast-123``;
      the trailing ``/`` and ``:`` markers enforce a boundary.

    Matches the uWSGI vassal/workers by their procname prefix ``<name>:`` and
    the app's own processes by ``apps/<name>/`` in the cmdline or cwd. Never
    matches the shared Emperor (its cwd/cmdline is not under any app dir).
    """
    return (
        f"{app_name}:" in cmdline
        or f"apps/{app_name}/" in cmdline
        or f"apps/{app_name}/" in cwd
    )


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
        # Note: The background state sync service may have already transitioned
        # the app to RUNNING if it detected processes started. Handle gracefully.
        if self.app.run_state != AppStateEnum.RUNNING:
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
        """Stops the app by removing its uWSGI .ini files from the enabled directory.

        After removing config files, waits for old processes to terminate.
        This ensures the uWSGI Emperor fully cleans up the old vassal,
        including resetting any throttle state from crashed daemons.
        """
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

        # Wait for the Emperor to fully terminate the old vassal processes.
        # This is critical: without this wait, the Emperor may still have
        # throttle state from a previously crashing daemon, causing the new
        # vassal to start with accumulated respawn delays.
        self._wait_for_processes_to_stop()

        # Complete transition: STOPPING -> STOPPED
        self.app._transition_state(AppStateEnum.STOPPED)  # noqa: SLF001
        log(f"App '{self.app.name}' stopped.", level=2, fg="green")

    def _app_pids(self) -> list[int]:
        """PIDs of every live process belonging to this app.

        Scans ``/proc`` and matches each process's cmdline and working
        directory (see :func:`_proc_belongs_to_app`). Catches Nix-store
        ``exec``'d daemons that ``pgrep -f apps/<name>`` misses — the
        leftover that holds a fixed port (e.g. owncast's RTMP 1935) and makes
        the next deploy fail. Returns ``[]`` where there is no procfs (a
        non-Linux dev machine), where there is nothing to reap anyway.
        """
        proc = Path("/proc")
        if not proc.is_dir():
            return []
        pids: list[int] = []
        for entry in proc.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                cmdline = (entry / "cmdline").read_bytes().replace(b"\x00", b" ")
            except OSError:
                continue  # process exited between listing and read
            cwd = ""
            # cwd unreadable (perms/gone) — the cmdline match still applies
            with suppress(OSError):
                cwd = os.readlink(entry / "cwd")
            if _proc_belongs_to_app(
                cmdline.decode("utf-8", "replace"), cwd, self.app.name
            ):
                pids.append(int(entry.name))
        return pids

    def _wait_for_processes_to_stop(
        self, timeout: float = _GRACEFUL_STOP_SECONDS
    ) -> None:
        """Block until none of the app's processes remain, force-killing any
        straggler so it cannot keep holding a port.

        Removing the ``.ini`` makes the Emperor stop the vassal, which should
        terminate the app's processes. We then *confirm* they are gone rather
        than guess — a leftover daemon binding a fixed port would otherwise
        make the next deploy of that app fail with an opaque health-check
        timeout (an order-dependent heisenbug). If any survive the graceful
        period (the Emperor didn't reap them, or the daemon ignored SIGTERM),
        we SIGTERM then SIGKILL them. Detection is precise to this app, and by
        this point the vassal is gone, so nothing respawns the daemon.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self._app_pids():
                time.sleep(0.5)  # brief grace for fd / port release
                return
            time.sleep(0.5)

        stragglers = self._app_pids()
        if not stragglers:
            return
        log(
            f"Force-stopping {len(stragglers)} leftover process(es) for "
            f"'{self.app.name}' (graceful stop timed out)",
            level=2,
            fg="yellow",
        )
        for sig in (signal.SIGTERM, signal.SIGKILL):
            for pid in self._app_pids():
                with suppress(OSError):
                    os.kill(pid, sig)
            time.sleep(1.0)

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
