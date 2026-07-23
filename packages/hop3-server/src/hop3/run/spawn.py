# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy.orm import object_session

from hop3.config import HOP3_ROOT, HOP3_USER, UWSGI_ENABLED
from hop3.core.artifacts import BuildArtifact
from hop3.core.env import Env
from hop3.core.plugins import get_proxy_strategy
from hop3.lib import (
    Diagnosis,
    abort_with_diagnosis,
    echo,
    get_free_port,
    log,
    log_diagnosis,
    shell,
)
from hop3.lib.logging import server_log
from hop3.lib.settings import write_settings
from hop3.project.config import AppConfig
from hop3.project.procfile import parse_procfile

from .uwsgi import spawn_uwsgi_worker

# A top-level Nix store path `/nix/store/<hash>-<name>` (the hash is 32 base-32
# chars). Stops at the next `/`, so `…-forgejo-11.0.1/bin/forgejo web` yields the
# store-path ROOT, which is what `nix-store -q --requisites` takes.
_NIX_STORE_PATH_RE = re.compile(r"/nix/store/[a-z0-9]{32}-[^\s/]+")


def _extract_nix_store_paths(commands) -> list[str]:
    """The distinct `/nix/store/<hash>-<name>` roots referenced by worker commands."""
    paths: set[str] = set()
    for cmd in commands:
        paths.update(_NIX_STORE_PATH_RE.findall(cmd or ""))
    return sorted(paths)


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
        """
        Initialize additional attributes for the application configuration.

        This sets up crucial paths and configuration for the application
        object by extracting necessary details from the `app` object, such as
        application name, paths, and environment settings.
        """
        self.app_name = self.app.name
        self.app_path = self.app.app_path
        self.virtualenv_path = self.app.virtualenv_path
        self.config = AppConfig.from_dir(self.app_path)
        self.artifact = self._load_artifact()
        self.env = self.make_env()

    def _load_artifact(self) -> BuildArtifact | None:
        """
        Load build artifact from disk if available.

        Returns:
            BuildArtifact if found and valid, None otherwise
        """
        artifact_path = self.app_path / "BUILD_ARTIFACT.json"
        artifact = BuildArtifact.load(artifact_path)
        if artifact:
            server_log.info(
                "Loaded build artifact",
                app_name=self.app_name,
                kind=artifact.kind,
                build_id=artifact.build_id,
            )
        else:
            server_log.debug(
                "No build artifact found, using legacy detection",
                app_name=self.app_name,
            )
        return artifact

    def _apply_artifact_runtime(self, env: Env) -> bool:
        """
        Apply runtime configuration from build artifact.

        Args:
            env: Environment to update

        Returns:
            True if artifact was applied, False otherwise
        """
        if not self.artifact or not self.artifact.runtime:
            return False

        runtime = self.artifact.runtime

        # Apply environment variables from artifact
        for key, value in runtime.env_vars.items():
            if key not in env:  # Don't override explicit user config
                env[key] = value

        # Prepend paths to PATH
        current_path = env.get("PATH", "")
        for path in runtime.path_prepend:
            if path and path not in current_path:
                env["PATH"] = f"{path}:{env.get('PATH', '')}"

        return True

    def _toolchain_owned_keys(self) -> set[str]:
        """
        Env keys owned by the build artifact's toolchain.

        These hold absolute, per-app, per-deploy paths (MIX_HOME, HEX_HOME, …)
        the toolchain bakes into the artifact runtime. A persisted [env] must
        never override them: a hardcoded value (another app's MIX_HOME) would
        point the runtime at a directory the toolchain never populated.
        """
        if not self.artifact or not self.artifact.runtime:
            return set()
        return set(self.artifact.runtime.env_vars)

    # Build/run-once hooks — never persistent processes, so they must never be
    # handed to uWSGI as daemons. Matches RuntimeManifestBuilder's filter.
    _LIFECYCLE_HOOKS = frozenset({"prebuild", "postbuild", "prerun"})

    @property
    def workers(self) -> dict:
        """
        Get worker definitions, preferring artifact over AppConfig.

        If a build artifact exists with runtime.workers, use those. Otherwise
        fall back to AppConfig.workers (legacy behavior).

        Either way, lifecycle hooks are filtered out: a Procfile ``prebuild:``
        is a build step, not a daemon. The fallback path used to leak it to
        uWSGI, which then respawned it forever — e.g. an Elixir app looping
        ``mix release --overwrite`` and racing the web worker for the freshly
        (re)written release binary (`bin/<app>: not found`).
        """
        if self.artifact and self.artifact.runtime.workers:
            workers = self.artifact.runtime.workers
        else:
            workers = self.config.workers
        return {k: v for k, v in workers.items() if k not in self._LIFECYCLE_HOOKS}

    @property
    def web_workers(self):
        """Get web workers, preferring artifact over AppConfig."""
        web_worker_names = {"wsgi", "jwsgi", "rwsgi", "web"}
        return {k: v for k, v in self.workers.items() if k in web_worker_names}

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
        """
        Setup proxy configuration.

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
            # Loud failure: surface a broken proxy/cert rather than reporting a
            # successful deploy with a missing or untrusted certificate.
            log(
                f"✗ Proxy setup failed for '{self.app_name}': {e}",
                level=0,
                fg="red",
            )
            server_log.exception(
                "Proxy setup failed", app_name=self.app_name, error=str(e)
            )
            raise

    def _calculate_worker_changes(self, worker_count: dict) -> tuple[dict, dict]:
        """
        Calculate which workers to create and destroy based on deltas.

        Returns:
            Tuple of (to_create, to_destroy) dictionaries
        """
        to_create = {}
        to_destroy = {}

        for env_key, count in worker_count.items():
            to_create[env_key] = range(1, count + 1)
            if self.deltas.get(env_key):
                to_create[env_key] = range(
                    1,
                    count + self.deltas[env_key] + 1,
                )
                if self.deltas[env_key] < 0:
                    to_destroy[env_key] = range(
                        count,
                        count + self.deltas[env_key],
                        -1,
                    )
                worker_count[env_key] += self.deltas[env_key]

        return to_create, to_destroy

    def _get_worker_counts(self, scaling) -> dict:
        """
        Get worker counts from configuration and scaling file.

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
        """
        Wait for old app processes to terminate after config removal.

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
                    check=False,
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

    def _run_before_run_commands(self, env: Env) -> None:
        """
        Execute before-run commands from the artifact.

        These commands run once before workers start, with the full runtime
        environment. Common uses: database migrations, cache warmup, etc.

        Args:
            env: Runtime environment for command execution

        Raises:
            RuntimeError: If any command fails
        """
        if not self.artifact or not self.artifact.runtime.before_run:
            # No artifact or no before-run commands
            return

        before_run = self.artifact.runtime.before_run
        if not before_run:
            return

        log(f"Running {len(before_run)} before-run command(s)...", level=1, fg="blue")
        server_log.info(
            "Executing before-run commands",
            app_name=self.app_name,
            command_count=len(before_run),
        )

        # Determine working directory
        working_dir = self.artifact.runtime.working_dir or str(self.app.src_path)

        for i, cmd in enumerate(before_run, 1):
            log(f"  [{i}/{len(before_run)}] {cmd}", level=1)
            try:
                # shell() handles logging and error reporting
                result = shell(
                    cmd,
                    cwd=working_dir,
                    env=dict(env),
                    timeout=300,  # 5 minute timeout per command
                    check=False,  # Handle errors ourselves for structured logging
                )
                if result.returncode != 0:
                    # Show error output to user
                    log(
                        f"  Command failed with exit code {result.returncode}",
                        level=0,
                        fg="red",
                    )
                    if result.stdout:
                        log("  stdout:", level=0, fg="red")
                        for line in result.stdout.strip().split("\n")[-20:]:
                            log(f"    {line}", level=0)
                    if result.stderr:
                        log("  stderr:", level=0, fg="red")
                        for line in result.stderr.strip().split("\n")[-20:]:
                            log(f"    {line}", level=0)
                    server_log.error(
                        "Before-run command failed",
                        app_name=self.app_name,
                        command=cmd,
                        exit_code=result.returncode,
                        stderr=result.stderr[:500] if result.stderr else None,
                    )
                    msg = f"Before-run command failed: {cmd}"
                    raise RuntimeError(msg)
                log("  Command completed successfully", level=2, fg="green")
            except subprocess.TimeoutExpired:
                log("  Command timed out after 5 minutes", level=0, fg="red")
                server_log.error(
                    "Before-run command timed out",
                    app_name=self.app_name,
                    command=cmd,
                )
                msg = f"Before-run command timed out: {cmd}"
                raise RuntimeError(msg) from None

        log("All before-run commands completed", level=1, fg="green")

    def _cleanup_stale_sockets(self) -> None:
        """
        Clean up stale socket files left behind by previous processes.

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

    def _verify_nix_closure_intact(self) -> None:
        """
        Fail loud, at deploy time, if a Nix app's runtime closure is broken.

        A nix wrapper execs hardcoded `/nix/store` paths (forgejo's wrapper execs
        `${forgejo}/bin/forgejo`). If a garbage-collect reclaimed any path in that
        closure, the worker dies "No such file or directory" and today only
        surfaces as a 180s health-check timeout. Checking the closure here turns
        that into an immediate, named error before uWSGI ever starts.

        Deploy-time, not build-time, on purpose: at build time the whole closure
        exists by construction (it was just realised) — the reclaim happens
        later, so a build-time check is vacuous for this class. Best-effort:
        aborts only on a POSITIVELY-missing path; if `nix-store` can't answer
        (not on PATH, times out, errors) it logs and continues — a guard that
        can't run must never block an otherwise-working deploy.
        """
        if not (self.artifact and self.artifact.kind == "nix"):
            return
        roots = _extract_nix_store_paths(self.workers.values())
        if not roots:
            return

        missing: list[str] = []
        for root in roots:
            if not os.path.exists(root):
                missing.append(root)
                continue
            try:
                result = subprocess.run(
                    ["nix-store", "-q", "--requisites", root],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired) as e:
                log(
                    f"Nix closure check skipped for '{self.app_name}' "
                    f"(nix-store unavailable: {e})",
                    level=2,
                    fg="yellow",
                )
                continue
            if result.returncode != 0:
                log(
                    f"Nix closure check inconclusive for '{self.app_name}': "
                    f"{result.stderr.strip()[:200]}",
                    level=2,
                    fg="yellow",
                )
                continue
            missing.extend(
                p for p in result.stdout.split() if p and not os.path.exists(p)
            )

        if missing:
            abort_with_diagnosis(
                Diagnosis(
                    component="uWSGI spawner",
                    action="start Nix app",
                    reason=(
                        f"'{self.app_name}' references {len(missing)} Nix store "
                        f"path(s) that no longer exist (garbage-collected): "
                        f"{missing[0]}"
                    ),
                    hint=(
                        "The runtime closure was reclaimed by a nix "
                        "garbage-collect. Redeploy to rebuild it — the installer "
                        "now pins auto-GC off (min-free = 0, nix-gc.timer "
                        "disabled) to prevent recurrence."
                    ),
                    troubleshooting=[
                        f"nix-store -q --requisites {roots[0]}",
                        f"hop3 app deploy --app {self.app_name}",
                    ],
                )
            )

    def spawn_app(self) -> None:
        """
        Create the app's workers by setting up web worker configurations and
        handling environment-specific setups, including nginx and uwsgi
        configurations.
        """
        # Determine worker source for logging
        if self.artifact and self.artifact.runtime.workers:
            worker_source = "artifact"
        else:
            worker_source = "legacy (AppConfig)"

        server_log.info(
            "Spawning app workers",
            app_name=self.app_name,
            workers=list(self.workers.keys()),
            worker_source=worker_source,
        )
        log(f"Workers ({worker_source}): {list(self.workers.keys())}", level=2)

        # Fail loud early if a Nix app's runtime closure was garbage-collected,
        # instead of letting the worker crash-loop into a 180s health-check
        # timeout (the forgejo class).
        self._verify_nix_closure_intact()

        # Early detection: Python app with no web-facing workers
        if not self.web_workers and self.artifact:
            kind = self.artifact.kind
            if kind in {"python", "buildpack", "virtualenv"}:
                log_diagnosis(
                    Diagnosis(
                        component="uWSGI spawner",
                        action="select web workers",
                        reason=(
                            "the Python app declares no web-facing workers; "
                            "uWSGI will start in no-workers mode and won't "
                            "serve HTTP requests"
                        ),
                        hint=(
                            "Add a worker to hop3.toml ([run.workers] "
                            'wsgi = "app:application") or to the Procfile '
                            "(web: gunicorn app:application -b 0.0.0.0:$PORT)"
                        ),
                    ),
                    fg="yellow",
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

        # Execute before-run commands from artifact
        self._run_before_run_commands(env)

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
        """
        Add src/ to PYTHONPATH for Python apps with src layout.

        This is a common pattern where packages live in src/package_name/
        (e.g., src-layout projects that ship their package under ``src/``)
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
        """
        Set up and configure the environment for the application.

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

        # Apply runtime config from build artifact (preferred)
        # Falls back to legacy detection if no artifact exists
        if not self._apply_artifact_runtime(env):
            # Legacy: detect language-specific paths at runtime
            self._setup_node_paths(env)
            self._setup_ruby_paths(env)
            self._setup_python_paths(env)

        # Load environment variables from the ORM (the persisted [env] block),
        # but never let them clobber a toolchain-owned absolute path. The build
        # artifact's runtime env_vars (MIX_HOME, HEX_HOME, …) are computed per
        # app, per deploy by the toolchain; a stale or hand-copied [env] value
        # (e.g. another app's MIX_HOME) would point the runtime at a directory
        # the toolchain never populated. This mirrors the precedence
        # RuntimeManifestBuilder already applies at build time: toolchain wins.
        toolchain_keys = self._toolchain_owned_keys()
        runtime_env = self.app.get_runtime_env()
        overridden = sorted(toolchain_keys & set(runtime_env))
        applied_env = {k: v for k, v in runtime_env.items() if k not in toolchain_keys}
        env.update(applied_env)
        if overridden:
            log(
                f"Ignoring [env] override of toolchain-owned {', '.join(overridden)} "
                f"for '{self.app_name}' — the build artifact's value wins",
                level=1,
                fg="yellow",
            )
            server_log.warning(
                "Ignored [env] override of toolchain-owned keys",
                app_name=self.app_name,
                keys=overridden,
            )
        server_log.info(
            "Loaded runtime env_vars from ORM",
            app_name=self.app_name,
            env_vars_count=len(applied_env),
            env_vars_keys=list(applied_env.keys()),
        )

        # Keep the app's port STABLE across redeploys: reuse the port already
        # persisted on the App (assigned on the first deploy) and only allocate
        # a fresh one when the app has none yet. A port that changes on every
        # deploy is the root cause of stale-nginx 502s — a redeploy that moves
        # the port but doesn't re-reach a successful proxy rewrite+reload leaves
        # nginx proxying the dead old port while the app is healthy on the new one.
        if "PORT" not in env:
            if self.app.port:
                port = env["PORT"] = str(self.app.port)
                log(f"Reusing assigned port: {port}", level=3)
            else:
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
        """
        Creates new workers for the given application.

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
        """
        Removes unnecessary worker configuration files based on the provided
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
