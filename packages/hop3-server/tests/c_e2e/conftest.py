# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Pytest configuration for Docker-based E2E tests."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import docker
import docker.errors
import httpx
import pytest
from hop3_testing.bundle import collect_diagnostic_bundle
from hop3_testing.results import ResultStore
from hop3_testing.targets.adapter import ContainerTarget
from hop3_testing.targets.constants import (
    E2E_TEST_SECRET_KEY,
    create_test_token,
    hermetic_cli_cwd,
)

FLASK_APP_CODE = """
from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "Hello from Flask!"

@app.route("/health")
def health():
    return {"status": "ok"}
"""

if TYPE_CHECKING:
    from collections.abc import Generator

# Note: test_full_deployment.py now uses Docker fixtures like other d_e2e tests
# No need to import c_system fixtures anymore


def pytest_configure(config):
    """Add custom markers."""
    config.addinivalue_line(
        "markers",
        "e2e: Full end-to-end tests requiring Docker containers",
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Stash each phase's report so the bundle finalizer can detect failures."""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"_rep_{rep.when}", rep)


@pytest.fixture(autouse=True)
def bundle_on_failure(request):
    """Collect a diagnostic bundle (ADR 043 §7) when a c_e2e test fails.

    Opt-in per test: set ``request.node.hop3_container`` (a docker-py container)
    and ``request.node.hop3_app`` (the deployed app name) when a bundle is
    wanted on failure. Fires in function teardown, before the class-scoped
    container is torn down, and prints the headline + persists the bundle so
    ``hop3-test why <run-id>`` can replay it.
    """
    yield
    rep_setup = getattr(request.node, "_rep_setup", None)
    rep_call = getattr(request.node, "_rep_call", None)
    failed = (rep_setup is not None and rep_setup.failed) or (
        rep_call is not None and rep_call.failed
    )
    if not failed:
        return
    container = getattr(request.node, "hop3_container", None)
    app = getattr(request.node, "hop3_app", None)
    if container is None or app is None:
        return
    try:
        target = ContainerTarget(container)
        bundle = collect_diagnostic_bundle(target, app, target_kind="docker")
    except Exception as e:  # diagnostics must never mask the test failure
        print(f"\n(diagnostic bundle collection failed: {e})")
        return
    print("\n" + bundle.headline)
    with contextlib.suppress(Exception):
        _persist_pytest_bundle(app, bundle)


def _persist_pytest_bundle(app: str, bundle: Any) -> None:
    """Persist a pytest-collected bundle so `hop3-test why <run-id>` can replay it.

    Builds the minimal TestResult shape ResultStore.save reads (a run-less row;
    `why` keys on bundle_run_id, not the run).
    """
    test = SimpleNamespace(
        name=app,
        runner_type="c_e2e",
        tier=SimpleNamespace(value="e2e"),
        priority=SimpleNamespace(value="P0"),
    )
    result = SimpleNamespace(
        bundle=bundle,
        passed=False,
        total_duration=0.0,
        error=bundle.classifier,
        deploy_logs="",
        validation_results=[],
        test=test,
    )
    ResultStore().save(cast("Any", result))


@pytest.fixture(scope="session")
def docker_client(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[docker.DockerClient]:
    """Provide a Docker client for tests.

    Point ``DOCKER_CONFIG`` at a copy of the user's config with the
    credential-helper directives (``credsStore``/``credHelpers``) stripped, so
    building or pulling public images never shells out to a credential helper
    (e.g. ``docker-credential-osxkeychain``) — which pops an interactive keychain
    prompt and fails the run if declined (docker-py's ``build()`` eagerly
    resolves all credentials). The docker context (``currentContext``) and inline
    ``auths`` are preserved, so connectivity is unchanged.
    """
    cfg_dir = tmp_path_factory.mktemp("docker-config")
    real_cfg = Path.home() / ".docker" / "config.json"
    data: dict[str, Any] = {}
    if real_cfg.exists():
        with contextlib.suppress(OSError, ValueError):
            data = json.loads(real_cfg.read_text())
    data.pop("credsStore", None)
    data.pop("credHelpers", None)
    (cfg_dir / "config.json").write_text(json.dumps(data))

    prev = os.environ.get("DOCKER_CONFIG")
    os.environ["DOCKER_CONFIG"] = str(cfg_dir)
    try:
        client = docker.from_env()
        client.ping()  # connectivity check (context preserved)
        yield client
        client.close()
    finally:
        if prev is None:
            os.environ.pop("DOCKER_CONFIG", None)
        else:
            os.environ["DOCKER_CONFIG"] = prev


# Label carrying a content hash of everything the image bakes in. Reuse is
# gated on it, so the cached image can never silently test stale code.
_SRC_HASH_LABEL = "cloud.hop3.e2e-src-hash"


def _e2e_build_inputs() -> list[Path]:
    """Every file whose content the e2e image bakes in (COPY / ``pip install -e``).

    Covers the e2e Dockerfile + entrypoint and the ``pyproject.toml`` / ``README``
    / full ``src`` tree of hop3-server and hop3-rootd — including non-``.py`` data
    files (e.g. the WAF CRS rules the server loads at runtime). ``__pycache__`` is
    excluded (the Dockerfile strips it, and it isn't a build input).
    """
    project_root = Path(__file__).parents[4]
    docker_dir = Path(__file__).parent / "docker"
    inputs = [docker_dir / "Dockerfile", docker_dir / "entrypoint.sh"]
    for pkg in ("hop3-server", "hop3-rootd"):
        base = project_root / "packages" / pkg
        inputs.append(base / "pyproject.toml")
        inputs.append(base / "README.md")
        inputs += [
            p
            for p in (base / "src").rglob("*")
            if p.is_file() and "__pycache__" not in p.parts
        ]
    return inputs


def _compute_e2e_src_hash() -> str:
    """SHA-256 over the build inputs (relative path + bytes), truncated."""
    project_root = Path(__file__).parents[4]
    digest = hashlib.sha256()
    for path in sorted(_e2e_build_inputs()):
        digest.update(path.relative_to(project_root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:16]


@pytest.fixture(scope="session")
def hop3_image(docker_client: docker.DockerClient) -> str:
    """Build the hop3 E2E test image, reusing it only when it is up to date.

    The image bakes hop3-server + hop3-rootd source (and the e2e Dockerfile) at
    build time. We stamp the build with a content hash of those inputs
    (``_SRC_HASH_LABEL``) and reuse the cached image only when the hash still
    matches — so a ``git pull`` or a source edit can never silently test stale
    code (the class of bug where a WAF deploy went "green" against a server with
    no WAF support). ``HOP3_E2E_FORCE_REBUILD=1`` forces a rebuild regardless.
    """
    image_tag = "hop3-e2e:test"
    src_hash = _compute_e2e_src_hash()

    if not os.environ.get("HOP3_E2E_FORCE_REBUILD"):
        try:
            existing = docker_client.images.get(image_tag)
        except docker.errors.ImageNotFound:
            existing = None
        if existing is not None:
            baked = (existing.labels or {}).get(_SRC_HASH_LABEL)
            if baked == src_hash:
                print(f"Using existing Docker image: {image_tag} (src {src_hash})")
                return image_tag
            print(
                f"Rebuilding {image_tag}: baked source {baked or '<none>'} != "
                f"current {src_hash} — server/rootd/Dockerfile changed since the "
                f"cached image was built."
            )

    # Build the image. The Dockerfile copies source and installs with
    # ``pip install -e``, so the build always reflects the current tree.
    print(f"Building Docker image: {image_tag} (src {src_hash})")
    print("This may take 5-10 minutes on first run...")

    project_root = Path(__file__).parents[4]
    dockerfile_path = Path(__file__).parent / "docker" / "Dockerfile"

    try:
        _image, logs = docker_client.images.build(
            path=str(project_root),
            dockerfile=str(dockerfile_path),
            tag=image_tag,
            labels={_SRC_HASH_LABEL: src_hash},
            rm=True,  # Remove intermediate containers
            forcerm=True,  # Always remove intermediate containers
        )

        # Print build logs
        for log in logs:
            if "stream" in log:
                print(log["stream"].strip())

        print(f"Successfully built image: {image_tag}")
        return image_tag

    except docker.errors.BuildError as e:
        print(f"Build failed: {e}")
        for log in e.build_log:
            if "stream" in log:
                print(log["stream"].strip())
        msg = f"Failed to build Docker image: {e}"
        raise AssertionError(msg)


def _start_hop3_container(
    docker_client: docker.DockerClient, image: str, label: str = "hop3"
) -> dict[str, Any]:
    """Start a single hop3 container and wait for it to be ready.

    Returns a container_info dict with `container`, `ssh_host`, `ssh_port`,
    `ssh_key` (path), `http_base`, and `api_url`. Raises on failure (after
    dumping diagnostic logs). Caller is responsible for teardown via
    `_stop_hop3_container`.

    `label` is used only in print output to distinguish concurrent
    containers (e.g. "A" / "B" for the migration-test pair).
    """
    print(f"\n--- Starting hop3 container [{label}] ---")
    container = docker_client.containers.run(
        image,
        detach=True,
        ports={
            "22/tcp": None,  # SSH - random port
            "80/tcp": None,  # HTTP - random port
            "8000/tcp": None,  # Hop3 server - random port
        },
    )

    # Wait for services to initialize
    print(f"[{label}] Waiting for services to initialize...")
    time.sleep(5)

    container.reload()
    if container.status != "running":
        print(f"\n❌ [{label}] Container exited with status: {container.status}")
        print("Container logs:")
        print(container.logs().decode())
        with contextlib.suppress(Exception):
            container.remove(force=True)
        pytest.fail(f"[{label}] Container failed to start (status: {container.status})")

    # Wait for hop3-server to be ready
    print(f"[{label}] Waiting for hop3-server to be ready...")
    max_wait = 60
    start_time = time.time()

    while time.time() - start_time < max_wait:
        container.reload()
        if container.status != "running":
            print(f"\n❌ [{label}] Container exited during startup: {container.status}")
            print("Container logs:")
            print(container.logs().decode())
            with contextlib.suppress(Exception):
                container.remove(force=True)
            pytest.fail(f"[{label}] Container stopped unexpectedly")

        try:
            result = container.exec_run(
                "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/ || echo '000'"
            )
            # Accept 200 (OK) or 404 (no route but server responding)
            if b"200" in result.output or b"404" in result.output:
                print(f"✓ [{label}] hop3-server is responding")
                break
        except Exception as e:
            print(f"[{label}] Warning: Failed to check server health: {e}")

        time.sleep(2)
    else:
        print(f"\n⚠ [{label}] hop3-server did not start in time")
        _dump_supervisor_logs(container, label)
        print(f"\n[{label}] Container logs:")
        print(container.logs().decode())
        with contextlib.suppress(Exception):
            container.remove(force=True)
        pytest.fail(f"[{label}] hop3-server failed to start")

    container.reload()
    ports = container.attrs["NetworkSettings"]["Ports"]
    ssh_port = ports["22/tcp"][0]["HostPort"]
    http_port = ports["80/tcp"][0]["HostPort"]
    api_port = ports["8000/tcp"][0]["HostPort"]

    # Get SSH key for passwordless access. The path includes container.short_id
    # so concurrent containers don't collide on the same /tmp file.
    ssh_key_result = container.exec_run("cat /home/hop3/.ssh/id_rsa")
    ssh_key = ssh_key_result.output.decode()
    ssh_key_path = Path("/tmp") / f"hop3-e2e-key-{container.short_id}"
    ssh_key_path.write_text(ssh_key)
    ssh_key_path.chmod(0o600)

    info = {
        "container": container,
        "label": label,
        "ssh_host": "hop3@localhost",
        "ssh_port": int(ssh_port),
        "ssh_key": str(ssh_key_path),
        "ssh_key_path": ssh_key_path,
        "http_base": f"http://localhost:{http_port}",
        "api_url": f"http://localhost:{api_port}",
    }

    print(f"\n[{label}] Container ready:")
    print(f"  SSH: ssh -i {ssh_key_path} -p {ssh_port} hop3@localhost")
    print(f"  HTTP: {info['http_base']}")
    print(f"  API:  {info['api_url']}")

    return info


def _dump_supervisor_logs(container: Any, label: str) -> None:
    """Print supervisor stdout/stderr logs from a failed container."""
    for log_path, stream_name in (
        ("/var/log/supervisor/hop3-server.log", "stdout"),
        ("/var/log/supervisor/hop3-server_err.log", "stderr"),
    ):
        print(f"\n[{label}] Supervisor {stream_name} logs ({log_path}):")
        try:
            result = container.exec_run(f"cat {log_path}")
            print(result.output.decode())
        except Exception as e:
            print(f"Could not read {log_path}: {e}")


def _stop_hop3_container(info: dict[str, Any]) -> None:
    """Stop and remove a container started by `_start_hop3_container`. Idempotent."""
    label = info.get("label", "?")
    container = info["container"]
    print(f"\n[{label}] Stopping container...")
    try:
        container.reload()
        if container.status == "running":
            container.stop(timeout=10)
        container.remove(force=True)
    except Exception as e:
        print(f"[{label}] Warning: Error stopping container: {e}")

    ssh_key_path = info.get("ssh_key_path")
    if ssh_key_path is not None and ssh_key_path.exists():
        ssh_key_path.unlink()

    print(f"[{label}] Container stopped and removed.")


@pytest.fixture(scope="class")
def hop3_container(
    docker_client: docker.DockerClient, hop3_image: str
) -> Generator[dict[str, Any]]:
    """Start a hop3 container for E2E tests.

    Scope: class - new container for each test class.
    """
    print("\n" + "=" * 60)
    print("Starting hop3 E2E test container...")
    print("=" * 60)

    info = _start_hop3_container(docker_client, hop3_image, label="hop3")
    print("=" * 60 + "\n")
    try:
        yield info
    finally:
        _stop_hop3_container(info)


@pytest.fixture(scope="class")
def hop3_container_pair(
    hop3_image: str,
) -> Generator[tuple[Any, Any]]:
    """Yield two independent ``DockerTarget`` instances (A, B) for migration tests.

    Both targets are built from the pre-built ``hop3-e2e:test`` image (the
    `hop3_image` fixture). Each target gets a separate container_name to
    avoid Docker name collisions. Class-scoped so multiple tests in a
    single class reuse the pair.

    ``DockerTarget`` (from hop3-testing) is the right abstraction here —
    its ``run_command()`` prefers the direct HTTP API (`HOP3_API_URL=http://...`
    + `HOP3_API_TOKEN`), bypassing the SSH tunnel which is rejected by
    sshd's ``no-port-forwarding`` directive in the hop3-server-managed
    authorized_keys. This is the same path ``test_backup.py`` uses via
    its (single-instance) ``deployment_target`` fixture.
    """
    from hop3_testing.targets import (  # ruff:ignore[import-outside-top-level]
        DockerConfig,
        DockerTarget,
    )

    print("\n" + "=" * 60)
    print("Starting hop3 E2E test container PAIR (A + B)...")
    print("=" * 60)

    a = DockerTarget(
        DockerConfig(image=hop3_image, container_name="hop3-migrate-a"),
    )
    a.start()

    try:
        b = DockerTarget(
            DockerConfig(image=hop3_image, container_name="hop3-migrate-b"),
        )
        b.start()
    except Exception:
        a.stop()
        raise

    print("=" * 60 + "\n")
    try:
        yield (a, b)
    finally:
        # Tear down in reverse order; both must run even if one fails.
        try:
            b.stop()
        finally:
            a.stop()


#: Where Hop3's BackupManager persists backups inside the container, per
#: ``HopConfig.BACKUP_ROOT = HOP3_ROOT / 'backups'`` and
#: ``BackupManager._get_backup_dir`` (``apps/<app>/<id>``). Hardcoded here
#: rather than imported from hop3-server because this conftest is a test
#: harness — coupling on the layout is acceptable; coupling on the
#: server code's lifecycle would be worse.
BACKUP_DIR_IN_CONTAINER = "/home/hop3/backups/apps"


def transfer_backup_dir(src: Any, dst: Any, app_name: str) -> None:
    """Copy the entire backup tree for `app_name` from src target to dst.

    Streams ``/home/hop3/backups/apps/<app_name>/`` out of `src`'s
    container as a tar archive (via Docker's get_archive API) and
    unpacks it under ``/home/hop3/backups/apps/`` on `dst`'s container.
    After the copy, `dst` sees every backup that existed for `app_name`
    on `src`.

    Both containers must be built from the same image so the hop3 uid
    matches; we still chown after the unpack as defense-in-depth.

    Args:
        src: source ``DockerTarget``
        dst: destination ``DockerTarget``
        app_name: app whose backups should be transferred
    """
    src_container = src._container_helper.container
    dst_container = dst._container_helper.container
    src_path = f"{BACKUP_DIR_IN_CONTAINER}/{app_name}"
    dst_parent = BACKUP_DIR_IN_CONTAINER

    # Stream the source directory as a tar archive. The archive's top-level
    # entry is the leaf name (`<app_name>/...`), so unpacking under
    # /var/hop3/backups/apps/ recreates the directory at its original path.
    stream, _stat = src_container.get_archive(src_path)
    archive_bytes = b"".join(stream)

    # The destination's BackupManager creates /home/hop3/backups lazily
    # on first use. If no backup has been taken on dst yet, the parent
    # dir may not exist — put_archive requires it. Created as root since
    # docker exec defaults to root; we chown back to hop3 below.
    dst_container.exec_run(["mkdir", "-p", dst_parent])
    dst_container.put_archive(dst_parent, archive_bytes)

    # chown the *whole* backup root, not just the unpacked path. The
    # parent dirs we just created with `mkdir -p` are root-owned;
    # without this fix, a subsequent `hop3 backup create` on dst (which
    # runs as the hop3 user) hits Permission-denied on the parent. The
    # tar archive preserves per-file ownership but doesn't help us with
    # the freshly-mkdir'd ancestors.
    dst_container.exec_run(
        ["chown", "-R", "hop3:hop3", "/home/hop3/backups"], user="root"
    )


@pytest.fixture
def test_app_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for test applications."""
    app_dir = tmp_path / "test-app"
    app_dir.mkdir()
    return app_dir


def run_hop3_command(
    container_info: dict[str, Any], *args: str
) -> subprocess.CompletedProcess:
    """Run a hop3 CLI command against the container.

    Args:
        container_info: Container information dict from hop3_container fixture
        *args: Arguments to pass to hop3 command

    Returns:
        CompletedProcess with stdout, stderr, and returncode
    """
    ssh_key = container_info["ssh_key"]
    ssh_port = container_info["ssh_port"]

    # Set environment for hop3 CLI
    env = os.environ.copy()
    env["HOP3_API_URL"] = f"ssh://hop3@localhost:{ssh_port}"
    env["HOP3_SSH_KEY"] = ssh_key
    # Use the same secret key configured in the container
    env["HOP3_SECRET_KEY"] = "e2e-test-secret-key-do-not-use-in-production"

    cmd = ["hop3", *args]

    result = subprocess.run(
        cmd,
        check=False,
        env=env,
        capture_output=True,
        text=True,
    )

    return result


@pytest.fixture
def hop3_command(hop3_container: dict[str, Any]):
    """Provide a helper to run hop3 commands."""

    def _run(*args: str) -> subprocess.CompletedProcess:
        return run_hop3_command(hop3_container, *args)

    return _run


# ============================================================================
# Deployment Helpers
# ============================================================================


def init_git_repo(app_dir: Path) -> None:
    """Initialize git repository with test app files.

    Args:
        app_dir: Directory containing app files to commit
    """
    # Create isolated git environment to avoid picking up parent repo
    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@test.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@test.com",
    })
    # Unset variables that might point to parent repo
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    # Prevent git from looking in parent directories
    env["GIT_CEILING_DIRECTORIES"] = str(app_dir.parent)

    subprocess.run(
        ["git", "init"], cwd=app_dir, check=True, capture_output=True, env=env
    )
    subprocess.run(
        ["git", "add", "."], cwd=app_dir, check=True, capture_output=True, env=env
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=app_dir,
        check=True,
        capture_output=True,
        env=env,
    )


def cli_env(hop3_container: dict[str, Any]) -> dict[str, str]:
    """Env for ``hop3`` CLI calls against the container's JWT-authenticated HTTP
    API. The SSH tunnel is rejected by the hop3-managed authorized_keys, so
    deploys/commands authenticate with a real token (mirrors DeploymentSession).
    """
    env = os.environ.copy()
    env["HOP3_API_URL"] = hop3_container["api_url"]
    env["HOP3_API_TOKEN"] = create_test_token(secret_key=E2E_TEST_SECRET_KEY)
    env["HOP3_SECRET_KEY"] = E2E_TEST_SECRET_KEY
    env["HOP3_NO_INPUT"] = "1"  # skip the ADR-042 confirm prompt (non-tty run)
    return env


def deploy_app_dir(
    hop3_container: dict[str, Any],
    app_dir: Path,
    app_name: str,
    timeout: int = 600,
) -> subprocess.CompletedProcess:
    """Deploy a local app directory: ``hop3 deploy --app <name> <dir>``.

    The dir must be a git repo (hop3 deploy expects one) — call ``init_git_repo``
    first. Returns the CompletedProcess so callers can assert on returncode/output.

    Runs from ``hermetic_cli_cwd()`` (a dir with no ``hop3.toml`` ancestry): the
    deploy targets the app explicitly via ``--app`` + an explicit dir, so it needs
    no project context from the CWD. Without this, a stray ``hop3.toml`` in the
    pytest launch dir (e.g. the repo root's gitignored testlab config) makes the
    ADR-042 project-mismatch guard veto the deploy. Mirrors how ``hop3-testing``
    launches every harness ``hop3`` subprocess.
    """
    return subprocess.run(
        ["hop3", "deploy", "--app", app_name, str(app_dir)],
        env=cli_env(hop3_container),
        cwd=hermetic_cli_cwd(),
        capture_output=True,
        text=True,
        errors="replace",  # deploy output (pip/build) may not be valid UTF-8
        check=False,
        timeout=timeout,
    )


def deploy_flask_app(
    hop3_container: dict[str, Any],
    test_app_dir: Path,
    app_name: str,
    app_code: str | None = None,
    env_vars: dict[str, str] | None = None,
    procfile_content: str | None = None,
    extra_files: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Build a minimal Flask app in ``test_app_dir`` and deploy it.

    ``extra_files`` writes additional files (e.g. a ``hop3.toml`` carrying a
    ``[waf]`` section) into the app before deploy. Returns the deploy
    CompletedProcess — assert ``returncode == 0``.
    """
    (test_app_dir / "app.py").write_text(app_code or FLASK_APP_CODE)
    (test_app_dir / "requirements.txt").write_text("flask>=3.0\n")
    # uwsgi sets chdir automatically, so no 'cd' needed.
    (test_app_dir / "Procfile").write_text(
        procfile_content or "web: flask --app app run --host 0.0.0.0 --port $PORT\n"
    )
    if env_vars:
        (test_app_dir / "ENV").write_text(
            "\n".join(f"{k}={v}" for k, v in env_vars.items()) + "\n"
        )
    for name, content in (extra_files or {}).items():
        (test_app_dir / name).write_text(content)

    init_git_repo(test_app_dir)
    return deploy_app_dir(hop3_container, test_app_dir, app_name)


def wait_for_app_status(
    hop3_command,
    app_name: str,
    expected_states: list[str] | None = None,
    timeout: int = 60,
) -> bool:
    """Poll app:status until app reaches expected state.

    Args:
        hop3_command: The hop3_command fixture
        app_name: Name of the app to check
        expected_states: List of acceptable states (default: ["RUNNING"])
        timeout: Maximum wait time in seconds

    Returns:
        True if app reached expected state, False if timeout
    """
    if expected_states is None:
        expected_states = ["RUNNING"]

    print(f"Waiting for app '{app_name}' to reach state: {expected_states}")
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            result = hop3_command("app", "status", app_name)
            if result.returncode == 0:
                stdout = result.stdout.upper()
                if any(state in stdout for state in expected_states):
                    print(f"✓ App '{app_name}' reached expected state")
                    return True
        except Exception as e:
            print(f"  Warning: Error checking app status: {e}")

        time.sleep(2)

    print(f"✗ Timeout waiting for app '{app_name}' to reach {expected_states}")
    return False


def wait_for_http_ready(
    url: str,
    expected_status: int = 200,
    expected_content: str | None = None,
    timeout: int = 60,
    headers: dict[str, str] | None = None,
) -> tuple[bool, str]:
    """Poll HTTP endpoint until it's ready.

    Args:
        url: URL to poll
        expected_status: Expected HTTP status code (default: 200)
        expected_content: Optional content to look for in response
        timeout: Maximum wait time in seconds
        headers: Optional HTTP headers (e.g., {"Host": "example.com"})

    Returns:
        Tuple of (success: bool, error_message: str)
    """
    print(f"Waiting for HTTP endpoint: {url}")
    start_time = time.time()
    last_error = None

    while time.time() - start_time < timeout:
        try:
            response = httpx.get(
                url, headers=headers or {}, timeout=2.0, follow_redirects=True
            )

            if response.status_code == expected_status:
                if expected_content is None or expected_content in response.text:
                    print(f"✓ HTTP endpoint ready: {url}")
                    return True, ""
                print("  Content check failed, retrying...")

            elif response.status_code == 502:
                # Backend not ready yet
                print("  Backend not ready (502), retrying...")

            else:
                print(f"  Unexpected status {response.status_code}, retrying...")

        except (httpx.HTTPError, httpx.ConnectError) as e:
            last_error = str(e)
            print(f"  Connection error: {e}")

        time.sleep(1)

    error_msg = f"Timeout after {timeout}s. Last error: {last_error}"
    print(f"✗ {error_msg}")
    return False, error_msg


# ============================================================================
# Test App Creation Helpers
# ============================================================================


def create_flask_app(
    tmp_path: Path,
    name: str,
    response: str = "Hello",
    extra_imports: str = "",
    extra_code: str = "",
    requirements: str = "flask==3.0.0\n",
) -> Path:
    """Create a minimal Flask app for testing.

    Args:
        tmp_path: Base directory for app creation
        name: App directory name
        response: String to return from index route
        extra_imports: Additional import statements
        extra_code: Additional code in index function (before return)
        requirements: Contents of requirements.txt

    Returns:
        Path to created app directory
    """
    app_dir = tmp_path / name
    app_dir.mkdir()

    (app_dir / "requirements.txt").write_text(requirements)

    # Build app code
    imports = "from flask import Flask"
    if extra_imports:
        imports += f"\n{extra_imports}"

    code_lines = []
    if extra_code:
        for line in extra_code.strip().split("\n"):
            code_lines.append(f"    {line}")
        code_lines.append(f"    return {response!r}")
    else:
        code_lines.append(f"    return {response!r}")

    app_code = f"""{imports}

app = Flask(__name__)

@app.route("/")
def index():
{chr(10).join(code_lines)}
"""
    (app_dir / "app.py").write_text(app_code)
    (app_dir / "Procfile").write_text(
        "web: flask --app app run --host 0.0.0.0 --port $PORT\n"
    )

    return app_dir


# ============================================================================
# Backup Command Helpers
# ============================================================================


def extract_backup_id(stdout: str) -> str | None:
    """Extract backup ID from backup:create command output.

    Args:
        stdout: Command output containing "Backup ID: <id>"

    Returns:
        Backup ID string or None if not found
    """
    for line in stdout.split("\n"):
        if line.startswith("Backup ID:"):
            return line.split(":", 1)[1].strip()
    return None


def find_json_table(output: list[dict]) -> dict | None:
    """Find table data in JSON command output.

    Args:
        output: Parsed JSON output (list of message objects)

    Returns:
        Table dict with "rows" key, or None if not found
    """
    for item in output:
        if item.get("t") == "table":
            return item
    return None


def backup_in_table(backup_id: str, table: dict | None) -> bool:
    """Check if backup ID appears in table rows.

    Args:
        backup_id: Backup ID to search for
        table: Table dict from find_json_table()

    Returns:
        True if backup_id found in any row
    """
    if not table:
        return False
    return any(backup_id in str(row) for row in table.get("rows", []))
