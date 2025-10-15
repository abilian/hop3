# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Pytest configuration for Docker-based E2E tests."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import docker
import docker.errors
import pytest

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


@pytest.fixture(scope="session")
def docker_client() -> Generator[docker.DockerClient, None, None]:
    """Provide Docker client for tests."""
    client = docker.from_env()
    # Test Docker connectivity
    client.ping()
    yield client
    client.close()


@pytest.fixture(scope="session")
def hop3_image(docker_client: docker.DockerClient) -> str:
    """Build hop3 E2E test image if not already built."""
    image_tag = "hop3-e2e:test"

    # Check if image already exists
    try:
        docker_client.images.get(image_tag)
        print(f"Using existing Docker image: {image_tag}")
        return image_tag
    except docker.errors.ImageNotFound:
        pass

    # Build the image
    print(f"Building Docker image: {image_tag}")
    print("This may take 5-10 minutes on first run...")

    project_root = Path(__file__).parent.parent.parent.parent.parent
    # Use simple Dockerfile that works on macOS (no systemd)
    dockerfile_path = Path(__file__).parent / "docker" / "Dockerfile"

    # NOTE: We no longer need to build the distribution!
    # The Dockerfile now copies source code and installs directly with 'pip install -e'
    # This ensures we always test the latest code without manual build steps

    # Build Docker image
    try:
        _image, logs = docker_client.images.build(
            path=str(project_root),
            dockerfile=str(dockerfile_path),
            tag=image_tag,
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


@pytest.fixture(scope="class")
def hop3_container(
    docker_client: docker.DockerClient, hop3_image: str
) -> Generator[dict[str, Any], None, None]:
    """Start a hop3 container for E2E tests.

    Scope: class - new container for each test class.
    """
    print("\n" + "=" * 60)
    print("Starting hop3 E2E test container...")
    print("=" * 60)

    # Start container (using supervisor, not systemd)
    container = docker_client.containers.run(
        hop3_image,
        detach=True,
        ports={
            "22/tcp": None,  # SSH - random port
            "80/tcp": None,  # HTTP - random port
            "8000/tcp": None,  # Hop3 server - random port
        },
    )

    try:
        # Wait for services to initialize
        print("Waiting for services to initialize...")
        time.sleep(5)

        # Check if container is still running
        container.reload()
        if container.status != "running":
            print(f"\n❌ Container exited with status: {container.status}")
            print("Container logs:")
            print(container.logs().decode())
            pytest.fail(f"Container failed to start (status: {container.status})")

        # Wait for hop3-server to be ready
        print("Waiting for hop3-server to be ready...")
        max_wait = 60
        start_time = time.time()

        while time.time() - start_time < max_wait:
            # Check container is still running
            container.reload()
            if container.status != "running":
                print(f"\n❌ Container exited during startup: {container.status}")
                print("Container logs:")
                print(container.logs().decode())
                pytest.fail(
                    f"Container stopped unexpectedly (status: {container.status})"
                )

            # Check if hop3-server is responding (check root endpoint)
            try:
                result = container.exec_run(
                    "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/ || echo '000'"
                )
                # Accept 200 (OK) or 404 (no route but server responding)
                if b"200" in result.output or b"404" in result.output:
                    print("✓ hop3-server is responding")
                    break
            except Exception as e:
                print(f"Warning: Failed to check server health: {e}")

            time.sleep(2)
        else:
            # Timeout - dump logs for debugging
            print("\n⚠ hop3-server did not start in time")
            print("\nSupervisor stdout logs:")
            try:
                result = container.exec_run("cat /var/log/supervisor/hop3-server.log")
                print(result.output.decode())
            except Exception as e:
                print(f"Could not get hop3-server stdout logs: {e}")

            print("\nSupervisor stderr logs:")
            try:
                result = container.exec_run(
                    "cat /var/log/supervisor/hop3-server_err.log"
                )
                print(result.output.decode())
            except Exception as e:
                print(f"Could not get hop3-server stderr logs: {e}")

            print("\nContainer logs:")
            print(container.logs().decode())
            pytest.fail("hop3-server failed to start")

        # Get container info
        container.reload()
        ports = container.attrs["NetworkSettings"]["Ports"]

        # Extract host ports
        ssh_port = ports["22/tcp"][0]["HostPort"]
        http_port = ports["80/tcp"][0]["HostPort"]
        api_port = ports["8000/tcp"][0]["HostPort"]

        # Get SSH key for passwordless access
        ssh_key_result = container.exec_run("cat /home/hop3/.ssh/id_rsa")
        ssh_key = ssh_key_result.output.decode()

        # Save SSH key to temp file
        ssh_key_path = Path("/tmp") / f"hop3-e2e-key-{container.short_id}"
        ssh_key_path.write_text(ssh_key)
        ssh_key_path.chmod(0o600)

        container_info = {
            "container": container,
            "ssh_host": "hop3@localhost",
            "ssh_port": int(ssh_port),
            "ssh_key": str(ssh_key_path),
            "http_base": f"http://localhost:{http_port}",
            "api_url": f"http://localhost:{api_port}",
        }

        print("\nContainer ready:")
        print(f"  SSH: ssh -i {ssh_key_path} -p {ssh_port} hop3@localhost")
        print(f"  HTTP: {container_info['http_base']}")
        print(f"  API: {container_info['api_url']}")
        print("=" * 60 + "\n")

        yield container_info

    finally:
        # Cleanup
        print("\nStopping container...")
        try:
            container.reload()
            if container.status == "running":
                container.stop(timeout=10)
            container.remove(force=True)
        except Exception as e:
            print(f"Warning: Error stopping container: {e}")

        # Remove SSH key
        if "ssh_key_path" in locals() and ssh_key_path.exists():
            ssh_key_path.unlink()

        print("Container stopped and removed.")


@pytest.fixture
def test_app_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for test applications."""
    app_dir = tmp_path / "test-app"
    app_dir.mkdir()
    return app_dir


@pytest.fixture
def deployed_flask_app(
    hop3_container: dict[str, Any], hop3_command, test_app_dir: Path
) -> Generator[dict[str, Any], None, None]:
    """Deploy a Flask app and automatically clean it up after the test.

    This fixture provides a complete deployment workflow:
    - Creates a simple Flask app
    - Initializes git repository
    - Creates tarball and deploys
    - Waits for app to be running
    - Automatically destroys app after test

    Yields:
        Dict with app info: {"name": str, "dir": Path, "url": str}
    """
    app_name = f"e2e-test-{int(time.time())}"

    # Deploy the app
    deploy_flask_app(hop3_container, test_app_dir, app_name)

    # Wait for app to be ready
    wait_for_app_status(hop3_command, app_name, timeout=60)

    # Get HTTP URL
    http_port = hop3_container["http_base"].split(":")[-1]
    app_url = f"http://localhost:{http_port}/"

    app_info = {
        "name": app_name,
        "dir": test_app_dir,
        "url": app_url,
        "hostname": f"{app_name}.test.local",
    }

    yield app_info

    # Automatic cleanup
    print(f"\nCleaning up app: {app_name}")
    try:
        hop3_command("app:destroy", app_name)
        print(f"✓ App {app_name} destroyed")
    except Exception as e:
        print(f"⚠ Warning: Failed to destroy app {app_name}: {e}")


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


def create_tarball(app_dir: Path, app_name: str) -> Path:
    """Create gzip-compressed tarball from git repo.

    Args:
        app_dir: Directory containing git repository
        app_name: Name for the tarball

    Returns:
        Path to created tarball
    """
    # Create isolated git environment to avoid picking up parent repo
    env = os.environ.copy()
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    # Prevent git from looking in parent directories
    env["GIT_CEILING_DIRECTORIES"] = str(app_dir.parent)

    tarball_path = Path(f"/tmp/{app_name}.tar.gz")
    # Explicitly specify git directory to avoid parent repo contamination
    git_dir = app_dir / ".git"
    subprocess.run(
        [
            "git",
            f"--git-dir={git_dir}",
            f"--work-tree={app_dir}",
            "archive",
            "--format=tar.gz",
            "-o",
            str(tarball_path),
            "HEAD",
        ],
        check=True,
        capture_output=True,
        env=env,
    )
    return tarball_path


def deploy_via_rpc(
    hop3_container: dict[str, Any], app_name: str, tarball_path: Path
) -> dict:
    """Deploy application via hop3 CLI command (no Python code dependency).

    Args:
        hop3_container: Container fixture with connection info
        app_name: Name of the app to deploy
        tarball_path: Path to tarball to deploy

    Returns:
        Deployment response dict (success status)
    """
    ssh_key = hop3_container["ssh_key"]
    ssh_port = hop3_container["ssh_port"]

    # Set environment for hop3 CLI
    env = os.environ.copy()
    env["HOP3_API_URL"] = f"ssh://hop3@localhost:{ssh_port}"
    env["HOP3_SSH_KEY"] = ssh_key
    env["HOP3_SECRET_KEY"] = "e2e-test-secret-key-do-not-use-in-production"

    # Deploy using hop3 CLI with tarball as stdin
    with open(tarball_path, "rb") as f:
        result = subprocess.run(
            ["hop3", "deploy", app_name],
            stdin=f,
            capture_output=True,
            check=False,
            env=env,
            timeout=60,
        )

    # Check if deployment succeeded
    if result.returncode != 0:
        print(
            f"Deployment failed (exit code {result.returncode}): {result.stderr.decode()}"
        )
        return {"status": "error", "message": result.stderr.decode()}

    return {"status": "success", "message": result.stdout.decode()}


def deploy_flask_app(
    hop3_container: dict[str, Any],
    test_app_dir: Path,
    app_name: str,
    app_code: str | None = None,
    env_vars: dict[str, str] | None = None,
    procfile_content: str | None = None,
) -> None:
    """Deploy a Flask app via RPC (complete helper).

    Args:
        hop3_container: Container fixture with connection info
        test_app_dir: Directory for app files
        app_name: Name of the app to deploy
        app_code: Optional custom Flask app code
        env_vars: Optional environment variables to write to ENV file
        procfile_content: Optional custom Procfile content
    """
    # Create Flask app
    if app_code is None:
        app_code = """
from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "Hello from Flask!"

@app.route("/health")
def health():
    return {"status": "ok"}
"""

    (test_app_dir / "app.py").write_text(app_code)
    (test_app_dir / "requirements.txt").write_text("flask>=3.0\n")

    # Create Procfile (uwsgi config sets chdir automatically, so no 'cd' needed)
    if procfile_content is None:
        procfile_content = "web: flask --app app run --host 0.0.0.0 --port $PORT\n"
    (test_app_dir / "Procfile").write_text(procfile_content)

    # Write environment variables if provided
    if env_vars:
        env_content = "\n".join(f"{k}={v}" for k, v in env_vars.items()) + "\n"
        (test_app_dir / "ENV").write_text(env_content)

    # Initialize git, create tarball, and deploy
    init_git_repo(test_app_dir)
    tarball_path = create_tarball(test_app_dir, app_name)
    response = deploy_via_rpc(hop3_container, app_name, tarball_path)
    print(f"Deploy response: {response}")


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
            result = hop3_command("app:status", app_name)
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
    import httpx

    print(f"Waiting for HTTP endpoint: {url}")
    start_time = time.time()
    last_error = None

    while time.time() - start_time < timeout:
        try:
            response = httpx.get(url, headers=headers or {}, timeout=2.0, follow_redirects=True)

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
