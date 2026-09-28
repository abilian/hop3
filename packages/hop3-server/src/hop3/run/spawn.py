# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
import shutil
import stat
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from sqlalchemy.orm import object_session

from hop3.config import UWSGI_ENABLED
from hop3.core.artifacts import ARTIFACT_FILENAME, BuildArtifact
from hop3.core.env import Env
from hop3.core.plugins import get_proxy_strategy
from hop3.lib import (
    Diagnosis,
    abort_with_diagnosis,
    echo,
    get_free_port,
    log,
    log_command_stream,
    log_diagnosis,
    shell,
)
from hop3.lib.logging import server_log
from hop3.lib.settings import write_settings
from hop3.project.config import AppConfig
from hop3.project.procfile import parse_procfile
from hop3.run.app_env import build_app_env
from hop3.run.served_tree import grant_web_server_read
from hop3.run.uwsgi.naming import vassal_glob, vassal_name
from hop3.toolchains.php_fpm import (
    POOL_CONFIG_NAME,
    POOL_TEMPLATE_NAME,
    render_pool_config,
)

from .nix_closure import (
    NIX_STORE_CANDIDATES,
    ClosureCheckError,
    missing_closure_paths,
    resolve_nix_store,
)
from .uwsgi import spawn_uwsgi_worker

# A top-level Nix store path `/nix/store/<hash>-<name>` (the hash is 32 base-32
# chars). Stops at the next `/`, so `…-forgejo-11.0.1/bin/forgejo web` yields the
# store-path ROOT, which is what `nix-store -q --requisites` takes.
_NIX_STORE_PATH_RE = re.compile(r"/nix/store/[a-z0-9]{32}-[^\s/]+")


def _extract_nix_store_paths(commands: Iterable[str]) -> list[str]:
    """The distinct `/nix/store/<hash>-<name>` roots referenced by worker commands."""
    paths: set[str] = set()
    for cmd in commands:
        paths.update(_NIX_STORE_PATH_RE.findall(cmd or ""))
    return sorted(paths)


def _through_volume_links(
    src: Path, dest: Path
) -> Callable[[str, list[str]], set[str]]:
    """
    A ``copytree`` ignore that never copies through a link already in ``dest``.

    Those links are the app's volumes, realized before this copy. Copying
    through one would put the store's pristine files over the app's data on
    every redeploy. An empty volume is seeded from the store instead, the way a
    volume is seeded from what a source tree ships at its target.
    """

    def ignore(directory: str, names: list[str]) -> set[str]:
        here = dest / Path(directory).relative_to(src)
        links = {name for name in names if (here / name).is_symlink()}
        for name in links:
            shipped = Path(directory) / name
            storage = (here / name).resolve()
            if shipped.is_dir() and storage.is_dir() and not any(storage.iterdir()):
                shutil.copytree(shipped, storage, dirs_exist_ok=True)
                _add_owner_write(storage)
        return links

    return ignore


def _add_owner_write(root: Path) -> None:
    """
    Make a copied store tree writable by its owner, ``root`` included.

    Store trees are read-only, and copytree preserves mode — including on the
    destination ITSELF, which came out 0555 and left the app directory
    impossible to write or clean up ("Permission denied: hop3.nix" on the next
    deploy's teardown). Failures are NOT suppressed: a tree the app cannot
    write to is the exact condition the writable tree exists to avoid, so it
    must not be discovered later as a puzzling application error.
    """
    for path in [root, *root.rglob("*")]:
        if not path.is_symlink():
            path.chmod(path.stat().st_mode | stat.S_IWUSR)


if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from hop3.orm import App


def spawn_app(app: App, deltas: dict[str, int] | None = None) -> None:
    """Create all workers for an app."""
    if deltas is None:
        deltas = {}
    launcher = AppLauncher(app, deltas)
    launcher.spawn_app()


def verify_nix_closure(app: App) -> None:
    """Abort if a Nix app's runtime closure has been reclaimed.

    Callable outside a spawn because a uWSGI *touch-restart* relaunches a vassal
    from its existing `.ini` without going through `spawn_app`. The guard used to
    live only on the spawn path, which left it one call short of the exact
    scenario it was written for: a garbage collection reclaims a closure, the app
    is restarted, and the vassal execs a store path that is no longer there.
    """
    AppLauncher(app).verify_nix_closure_intact()


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
        artifact_path = self.app_path / ARTIFACT_FILENAME
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
    def web_workers(self) -> dict:
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

    def _get_worker_counts(self, scaling: Path) -> dict:
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
            configs = list(UWSGI_ENABLED.glob(vassal_glob(self.app_name)))
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

    #: Written into the app directory once the store tree has been copied there,
    #: so a redeploy does not overwrite files the app (or its bootstrap) wrote.
    _WRITABLE_TREE_MARKER = ".hop3-writable-tree"

    #: Touched in the app's directory, outside src/, just before its workers
    #: start. A file in src/ newer than it was written by the running app or by
    #: what runs after it starts ([admin] and [probe] creation), and the next
    #: deploy that replaces src/ deletes it unless it lives in a volume. The
    #: test harness reads this; so could a deploy that warns before deleting.
    WORKERS_STARTED_MARKER: ClassVar[str] = ".hop3-workers-started"

    def _render_php_fpm_pool(self, env: Env) -> None:
        """
        Write the php-fpm pool's config, now that the port exists.

        The template is written at build time with a placeholder, because the
        port is allocated at deploy. Substituting it here — in Python, where
        the port has just been resolved — keeps the worker's command a single
        program, which is what uWSGI's ``attach-daemon`` wrapper requires: it
        prepends ``exec``, so a compound command puts ``exec`` on its first
        word and the rest never runs. That is precisely what the previous
        ``sed … && exec php-fpm`` did, and the pool never started once.

        Nothing caught it because no app had taken this path: all ten PHP
        recipes still declare ``[run].start``, which overrides this worker.
        """
        if not self.artifact or self.artifact.runtime.backend_protocol != "fastcgi":
            return

        template = self.app.app_path / POOL_TEMPLATE_NAME
        if not template.exists():
            abort_with_diagnosis(
                Diagnosis(
                    component="PHP toolchain",
                    action="configure the php-fpm pool",
                    reason=(
                        f"the build artifact says this app is served over "
                        f"FastCGI, but {template} — the pool config the "
                        f"toolchain writes at build time — is not there"
                    ),
                    hint=(
                        "The build did not complete as the artifact claims. "
                        "Redeploy; if it recurs, the build log is the place "
                        "to look."
                    ),
                )
            )

        port = env.get("PORT", "")
        if not port:
            abort_with_diagnosis(
                Diagnosis(
                    component="PHP toolchain",
                    action="configure the php-fpm pool",
                    reason=(
                        "no port was allocated for this app, so the pool has "
                        "no address to listen on"
                    ),
                    hint="This is a Hop3 bug: report it with the deploy log.",
                )
            )

        config = self.app.app_path / POOL_CONFIG_NAME
        config.write_text(render_pool_config(template.read_text(), port))
        log(f"php-fpm pool will listen on 127.0.0.1:{port}", level=2, fg="cyan")

        # nginx serves this app's document root for everything that is not a
        # .php script, and the source was extracted owner-only, so without
        # this every stylesheet, script and image is a 403 on an app that
        # otherwise deploys green. Scoped to the document root: what sits
        # above it stays unreadable, which is what a Laravel `.env` one level
        # up from `public/` depends on.
        document_root = env.get("PHP_DOCUMENT_ROOT", "")
        if document_root:
            grant_web_server_read(
                Path(document_root), (self.app.volumes_path, self.app.scratch_path)
            )

    def _materialize_writable_tree(self) -> None:
        """
        Copy a read-only build tree into the app's own directory.

        Some applications write inside their own install directory — a PHP app
        generating `config.php`, Matomo seeding `config/config.ini.php`. A Nix
        store path cannot support that, so the artifact names the tree and Hop3
        copies it here, at DEPLOY time.

        The timing is the whole point. This used to be a line in the generated
        wrapper, which runs when the app starts — after `[run] before-run`. So a
        bootstrap script ran against a directory holding the recipe and none of
        the application, and Matomo's installer died on `Failed opening required
        core/bootstrap.php` on a build that was otherwise correct.

        Copied ONCE. A redeploy that copied again would put the pristine tree
        back over a configuration the app has since written, silently reverting
        it; the marker is what stops that. Removing the marker forces a refresh.
        """
        source = self.artifact.runtime.writable_tree if self.artifact else ""
        if not source:
            return

        dest = self.app.src_path
        marker = dest / self._WRITABLE_TREE_MARKER
        if marker.exists():
            log(f"Writable tree already in place for '{self.app_name}'", level=3)
            return

        src = Path(source)
        if not src.is_dir():
            # Never silently skip: without the tree the app has no code, and the
            # bootstrap that follows would fail in a way that names the app.
            msg = (
                f"'{self.app_name}' declares a writable tree at {source}, which "
                f"does not exist. The build artifact and the Nix store disagree; "
                f"redeploy to rebuild it."
            )
            raise RuntimeError(msg)

        log(f"Materializing {source} into {dest}", level=2, fg="blue")
        shutil.copytree(
            src, dest, dirs_exist_ok=True, ignore=_through_volume_links(src, dest)
        )
        _add_owner_write(dest)
        marker.write_text(f"{source}\n")
        log(f"Writable tree ready for '{self.app_name}'", level=2, fg="green")

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
                    log_command_stream("stdout", result.stdout, level=0, fg="red")
                    log_command_stream("stderr", result.stderr, level=0, fg="red")
                    server_log.error(
                        "Before-run command failed",
                        app_name=self.app_name,
                        command=cmd,
                        exit_code=result.returncode,
                        stderr=result.stderr[:500] if result.stderr else None,
                    )
                    msg = f"Before-run command failed: {cmd}"
                    raise RuntimeError(msg)

                # A command that SUCCEEDED still has things to say, and this
                # threw all of them away. These commands are the app's headless
                # bootstrap — they report which account they created, or that
                # they found one already and left it alone. Uptime Kuma's says
                # in as many words when the admin Hop3 is about to advertise
                # does not exist in the database; that line was written every
                # deploy and read by nobody, while the smoke test's "the
                # credential Hop3 generated was refused" sent everyone looking
                # at the application instead. Output is evidence, not noise.
                log_command_stream("stdout", result.stdout, level=1)
                # stderr on a zero exit is a warning the script chose to raise.
                log_command_stream("stderr", result.stderr, level=0, fg="yellow")
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

    def verify_nix_closure_intact(self) -> None:
        """
        Fail loud, at deploy time, if a Nix app's runtime closure is broken.

        A nix wrapper execs hardcoded `/nix/store` paths (forgejo's wrapper execs
        `${forgejo}/bin/forgejo`). If a garbage-collect reclaimed any path in that
        closure, the worker dies "No such file or directory" and surfaces only as
        a 180s health-check timeout. Checking here turns that into an immediate,
        named error before uWSGI ever starts.

        Deploy-time, not build-time, on purpose: at build time the whole closure
        exists by construction (it was just realised) — the reclaim happens
        later, so a build-time check is vacuous for this class.

        **This guard never skips silently.** If `nix-store` cannot be located, or
        the query fails, the deploy aborts saying so. The earlier version logged
        and continued, on the reasoning that a guard which cannot run should not
        block an otherwise-working deploy; that is backwards. A guard that did
        not run has established nothing, and continuing as though it had is the
        silent-skip pattern this platform prohibits everywhere else. It also hid
        the guard's own breakage: `nix-store` is not on the deploy process's PATH
        on a normally-installed host, so the check logged a skip every time and
        never once fired.
        """
        # Gate on the BUILDER, not the artifact kind: the Nix builder emits a
        # `static` artifact for a site the proxy serves straight from the store,
        # and gating on `kind == "nix"` let that closure vanish unnoticed (the
        # e2e guard test found it the first time it ran). The artifact's own
        # location is a root too, so a worker line that names no store path
        # still gets its closure checked.
        if not self.artifact or "nix" not in {
            self.artifact.builder,
            self.artifact.kind,
        }:
            return
        roots = _extract_nix_store_paths([
            self.artifact.location,
            *self.workers.values(),
        ])
        if not roots:
            return

        nix_store = resolve_nix_store()
        if nix_store is None:
            abort_with_diagnosis(
                Diagnosis(
                    component="uWSGI spawner",
                    action="verify Nix closure",
                    reason=(
                        f"'{self.app_name}' is a Nix application, but `nix-store` "
                        f"could not be found, so its runtime closure cannot be "
                        f"checked."
                    ),
                    hint=(
                        "A Nix app cannot run without Nix present. Verify the "
                        "installation, or reinstall with `hop3-install server "
                        "--with nix`."
                    ),
                    troubleshooting=[
                        f"ls -l {NIX_STORE_CANDIDATES[0]}",
                        "command -v nix-store",
                    ],
                )
            )

        try:
            missing = missing_closure_paths(roots, nix_store)
        except ClosureCheckError as e:
            abort_with_diagnosis(
                Diagnosis(
                    component="uWSGI spawner",
                    action="verify Nix closure",
                    reason=(
                        f"the runtime closure of '{self.app_name}' could not be "
                        f"checked: {e}"
                    ),
                    hint=(
                        "The closure may or may not be intact — this is a "
                        "failure of the check, not of the app. Run the query "
                        "below by hand to see what Nix reports."
                    ),
                    troubleshooting=[
                        f"{nix_store} -q --requisites {roots[0]}",
                        f"hop3 app deploy --app {self.app_name}",
                    ],
                )
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
                        f"{nix_store} -q --requisites {roots[0]}",
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
        self.verify_nix_closure_intact()

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

        # BEFORE before-run: an app's bootstrap needs the application present.
        self._materialize_writable_tree()

        # BEFORE the workers exist: the pool's config names the port they will
        # be told to answer on, and the port is only settled a few lines above.
        self._render_php_fpm_pool(env)

        # Execute before-run commands from artifact
        self._run_before_run_commands(env)

        (self.app.app_path / self.WORKERS_STARTED_MARKER).touch()

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
        # The shared core (hop3.run.app_env, also behind `hop3 run` and
        # `hop3 app shell`): bootstrap, the artifact's toolchain env and PATH,
        # then the persisted [env] block, never over a toolchain-owned key. The
        # toolchain's env_vars (MIX_HOME, HEX_HOME, …) are absolute, per-app,
        # per-deploy paths; a stale or hand-copied [env] value (another app's
        # MIX_HOME) would point the runtime at a directory the toolchain never
        # populated. Same precedence RuntimeManifestBuilder applies at build time.
        env = Env(build_app_env(self.app, self.artifact, cwd=self.app_path))
        runtime_env = self.app.get_runtime_env()
        if self.artifact is None:
            # Legacy, pre-artifact app: detect language paths at runtime, then
            # let the persisted [env] win over them, as it always did.
            self._setup_node_paths(env)
            self._setup_ruby_paths(env)
            self._setup_python_paths(env)
            env.update(runtime_env)

        safe_defaults = {
            "NGINX_IPV4_ADDRESS": "0.0.0.0",
            "NGINX_IPV6_ADDRESS": "[::]",
            "BIND_ADDRESS": "127.0.0.1",
            # No default HOST_NAME - apps without hostname don't get proxy config
        }

        toolchain_keys = set(self.artifact.runtime.env_vars) if self.artifact else set()
        overridden = sorted(toolchain_keys & set(runtime_env))
        applied_env = {k: v for k, v in runtime_env.items() if k not in toolchain_keys}
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

        _ensure_php_server_concurrency(env, self.workers, self.app_name)

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

    def create_new_workers(self, to_create: dict, env: Env) -> None:
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
                enabled = UWSGI_ENABLED / vassal_name(self.app_name, kind, w)
                if enabled.exists():
                    # Skip if the worker configuration already exists
                    continue

                log(f"spawning '{self.app_name:s}:{kind:s}.{w:d}'", level=3)
                spawn_uwsgi_worker(self.app_name, kind, self.workers[kind], env, w)

    def remove_unnecessary_workers(self, to_destroy: dict) -> None:
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
                enabled = UWSGI_ENABLED / vassal_name(self.app_name, k, w)
                if not enabled.exists():
                    continue  # Skip if the file does not exist

                # Log the termination message with a specific log level and color
                msg = f"terminating '{self.app_name:s}:{k:s}.{w:d}'"
                log(msg, level=3, fg="yellow")
                enabled.unlink()  # Remove the worker's configuration file


# PHP's built-in server handles ONE request at a time unless told otherwise, and
# `php artisan serve` is that same server.
#
# The number should exceed what a BROWSER opens to one origin, not merely what
# breaks the self-request deadlock: Chromium and Firefox both keep up to six
# connections per origin alive, and at four workers a page whose last subresource
# is requested after load could find every worker held by an idle keep-alive
# socket. Eight leaves headroom above that six.
#
# This was raised from four while chasing paheko's hung screenshot, on the theory
# that starvation was why its page never finished painting. It was NOT: the
# capture timed out identically at four workers and at eight. The reasoning above
# stands on its own — a server that a browser can saturate is undersized — but it
# is not the explanation for paheko, and nothing here should be read as one.
PHP_BUILTIN_SERVER_WORKERS = "8"
_PHP_BUILTIN_SERVER_MARKERS = ("php -S", "artisan serve")


def _ensure_php_server_concurrency(
    env: Env, workers: dict[str, str], app_name: str
) -> None:
    """
    Give an app on PHP's built-in server more than one worker.

    `php -S` (and `php artisan serve`, which wraps it) is single-threaded. Any
    app that makes an HTTP request to ITSELF then deadlocks: the one worker is
    busy serving the page that is waiting for the reply, so the reply can never
    be produced. It is not a slow page — it is a hang that ends in a gateway
    timeout, and it looks exactly like the app being broken.

    Nextcloud does this (its richdocuments app fetches its own public URL) and
    served 504s after 60s; with workers it answered in 0.12s. Ten of the twenty
    catalog apps run on this server, so the fix belongs here rather than in each
    recipe.

    An explicit PHP_CLI_SERVER_WORKERS in the app's [env] wins — this only
    supplies the default that PHP itself should have.
    """
    if "PHP_CLI_SERVER_WORKERS" in env:
        return
    commands = " ".join(workers.values())
    if not any(marker in commands for marker in _PHP_BUILTIN_SERVER_MARKERS):
        return
    env["PHP_CLI_SERVER_WORKERS"] = PHP_BUILTIN_SERVER_WORKERS
    log(
        f"Running '{app_name}' on PHP's built-in server with "
        f"{PHP_BUILTIN_SERVER_WORKERS} workers (single-threaded by default, "
        f"which deadlocks an app that calls itself)",
        level=2,
    )
