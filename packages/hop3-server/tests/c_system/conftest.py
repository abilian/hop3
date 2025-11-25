# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Pytest fixtures for system integration tests using hop3-cli binary.

This module provides fixtures for system integration testing that:
- Start a Docker container with hop3-server for isolated testing
- Use the hop3-cli binary exclusively (no direct Python imports)
- Set up authentication with JWT tokens
- Test both tarball and git-hook deployment methods
- Clean up resources after tests
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import docker
import docker.errors
import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

E2E_TEST_USER = "system-test-user"
E2E_TEST_EMAIL = "system-test@example.com"
E2E_TEST_PASSWORD = "system-test-password-12345"

# Full infrastructure tests require explicit opt-in via environment variable
# These tests need uwsgi, nginx, systemd, etc.
_has_full_infrastructure = os.environ.get("HOP3_FULL_INFRASTRUCTURE", "").lower() in {
    "1",
    "true",
    "yes",
}

# Define skip marker for tests that require full deployment infrastructure
requires_full_infrastructure = pytest.mark.skipif(
    not _has_full_infrastructure,
    reason="Test requires full deployment infrastructure (uwsgi, nginx, systemd). "
    "Set HOP3_FULL_INFRASTRUCTURE=true to run these tests.",
)


@pytest.fixture(scope="session")
def docker_client() -> Generator[docker.DockerClient, None, None]:
    """Provide Docker client for tests."""
    client = docker.from_env()
    # Test Docker connectivity
    try:
        client.ping()
    except Exception as e:
        pytest.skip(f"Docker is not available: {e}")
    yield client
    client.close()


@pytest.fixture(scope="session")
def hop3_image(docker_client: docker.DockerClient) -> str:
    """Build or get hop3 E2E test image."""
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
    dockerfile_path = Path(__file__).parent.parent / "d_e2e" / "docker" / "Dockerfile"

    # Build Docker image
    try:
        _image, logs = docker_client.images.build(
            path=str(project_root),
            dockerfile=str(dockerfile_path),
            tag=image_tag,
            rm=True,
            forcerm=True,
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


@pytest.fixture(scope="session")
def local_server(
    docker_client: docker.DockerClient, hop3_image: str
) -> Generator[dict[str, Any], None, None]:
    """Start a Docker container with hop3-server for testing.

    Returns:
        Dict with container info including api_url and container object
    """
    print("\n=== Starting Docker Container ===")

    # Start container
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
            print(f"Container exited with status: {container.status}")
            print("Container logs:")
            print(container.logs().decode())
            pytest.fail(f"Container failed to start (status: {container.status})")

        # Wait for hop3-server to be ready
        print("Waiting for hop3-server to be ready...")
        max_wait = 60
        start_time = time.time()

        while time.time() - start_time < max_wait:
            container.reload()
            if container.status != "running":
                print(f"Container exited during startup: {container.status}")
                print("Container logs:")
                print(container.logs().decode())
                pytest.fail(
                    f"Container stopped unexpectedly (status: {container.status})"
                )

            # Check if hop3-server is responding
            try:
                result = container.exec_run(
                    "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/ || echo '000'"
                )
                if b"200" in result.output or b"404" in result.output:
                    print("✓ hop3-server is responding")
                    break
            except Exception as e:
                print(f"Warning: Failed to check server health: {e}")

            time.sleep(2)
        else:
            print("hop3-server did not start in time")
            print("\nContainer logs:")
            print(container.logs().decode())
            pytest.fail("hop3-server failed to start")

        # Get container info
        container.reload()
        ports = container.attrs["NetworkSettings"]["Ports"]

        # Extract host ports
        api_port = ports["8000/tcp"][0]["HostPort"]
        http_port = ports["80/tcp"][0]["HostPort"]

        api_url = f"http://localhost:{api_port}"

        print("Container ready:")
        print(f"  API: {api_url}")
        print(f"  HTTP: http://localhost:{http_port}")

        # Return dict similar to d_e2e but simpler (HTTP-only, no SSH)
        container_info = {
            "container": container,
            "api_url": api_url,
            "http_port": int(http_port),
        }

        yield container_info

    finally:
        # Cleanup
        print("\n=== Stopping Docker Container ===")
        try:
            container.reload()
            if container.status == "running":
                container.stop(timeout=10)
            container.remove(force=True)
            print("Container stopped and removed")
        except Exception as e:
            print(f"Warning: Error stopping container: {e}")


@pytest.fixture(scope="session")
def hop3_config_dir(local_server: dict[str, Any]) -> Generator[Path, None, None]:
    """Set up hop3-cli configuration via environment variables."""
    config_dir = Path(tempfile.mkdtemp(prefix="hop3-system-test-config-"))

    # Set API URL via environment variable (hop3-cli checks HOP3_API_URL)
    original_api_url = os.environ.get("HOP3_API_URL")
    original_secret_key = os.environ.get("HOP3_SECRET_KEY")

    # Use Docker container API
    api_url = local_server["api_url"]
    os.environ["HOP3_API_URL"] = api_url
    os.environ["HOP3_SECRET_KEY"] = "e2e-test-secret-key-do-not-use-in-production"

    print("\n=== Configuration ===")
    print(f"API URL: {api_url}")
    print(f"Config dir: {config_dir}")
    print(f"Test user: {E2E_TEST_USER}")

    yield config_dir

    # Cleanup
    if config_dir.exists():
        shutil.rmtree(config_dir)

    # Restore original environment
    if original_api_url:
        os.environ["HOP3_API_URL"] = original_api_url
    else:
        os.environ.pop("HOP3_API_URL", None)

    if original_secret_key:
        os.environ["HOP3_SECRET_KEY"] = original_secret_key
    else:
        os.environ.pop("HOP3_SECRET_KEY", None)


@pytest.fixture(scope="session")
def system_auth_token(hop3_config_dir: Path) -> Generator[str, None, None]:
    """Create test user and get authentication token."""
    print("\n=== Registering test user ===")
    print(f"Running: hop3 auth:register {E2E_TEST_USER} ...")

    # Register test user with timeout
    try:
        result = subprocess.run(
            ["hop3", "auth:register", E2E_TEST_USER, E2E_TEST_EMAIL, E2E_TEST_PASSWORD],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,  # 30 second timeout
        )
    except subprocess.TimeoutExpired:
        msg = (
            "Registration command timed out after 30 seconds. Check server connection."
        )
        raise AssertionError(msg)

    print(f"Registration exit code: {result.returncode}")
    if result.stdout:
        print(f"stdout: {result.stdout[:200]}")
    if result.stderr:
        print(f"stderr: {result.stderr[:200]}")

    # User might already exist from previous run, that's okay
    if result.returncode != 0:
        error_output = result.stderr + result.stdout
        if "already exists" not in error_output:
            if (
                "Authentication not enabled" in error_output
                or "auth" not in error_output.lower()
            ):
                pytest.skip("Authentication not enabled on server")
            pytest.fail(f"Failed to register test user: {error_output}")

    print("\n=== Logging in ===")
    print(f"Running: hop3 auth:login {E2E_TEST_USER} ...")

    # Login to get token with timeout
    try:
        result = subprocess.run(
            ["hop3", "auth:login", E2E_TEST_USER, E2E_TEST_PASSWORD],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,  # 30 second timeout
        )
    except subprocess.TimeoutExpired:
        pytest.fail(
            "Login command timed out after 30 seconds. Check server connection."
        )

    print(f"Login exit code: {result.returncode}")
    if result.stdout:
        print(f"stdout: {result.stdout[:200]}")
    if result.stderr:
        print(f"stderr: {result.stderr[:200]}")

    if result.returncode != 0:
        error_output = result.stderr + result.stdout
        if "Authentication not enabled" in error_output:
            pytest.skip("Authentication not enabled on server")
        pytest.fail(f"Failed to login: {error_output}")

    # Check if authentication is disabled
    # If "Authentication not enabled" appears in output, skip token extraction
    combined_output = result.stdout + result.stderr
    if "Authentication not enabled" in combined_output:
        print("\n=== Authentication not enabled on server - skipping token setup ===\n")
        yield ""  # Return empty string for token
        return

    # Extract token from output
    # Format can be:
    # 1. Old format: "Your API token:" followed by token on next line
    # 2. New format: "API token saved to /path/to/config.toml"
    token = None
    lines = result.stdout.split("\n")

    # Try to find token in old format
    for i, line in enumerate(lines):
        if "Your API token:" in line:
            # Token is on the next line
            if i + 1 < len(lines):
                token = lines[i + 1].strip()
                break

    # If token was saved to config file, we don't need to extract it
    # The CLI will read it from the config file automatically
    if not token and "API token saved to" in result.stdout:
        print("\n=== Token saved to config file by CLI ===")
        print("CLI will use token from config file automatically")
        # Return dummy token since we don't need to set it manually
        yield "token-saved-to-config"
        return

    if not token:
        # Debug output
        debug_info = f"""
Could not extract token from login output.

stdout:
{result.stdout}

stderr:
{result.stderr}

Looking for line containing 'Your API token:' followed by token on next line.
"""
        raise AssertionError(debug_info)

    print("\n=== Token extracted ===")
    print(f"Token (first 20 chars): {token[:20]}...")

    # Set token via environment variable (hop3-cli checks HOP3_API_TOKEN)
    os.environ["HOP3_API_TOKEN"] = token

    print("\n=== Authentication setup complete ===\n")

    yield token

    # Cleanup
    os.environ.pop("HOP3_API_TOKEN", None)

    # Logout after all tests
    subprocess.run(["hop3", "auth:logout"], check=False, capture_output=True)


# Keep old name for backward compatibility
e2e_auth_token = system_auth_token


@pytest.fixture
def test_app_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test app deployment."""
    app_dir = Path(tempfile.mkdtemp(prefix="hop3-e2e-app-"))
    yield app_dir
    if app_dir.exists():
        shutil.rmtree(app_dir)


@pytest.fixture
def deployed_app(
    e2e_auth_token: str, test_app_dir: Path
) -> Generator[dict, None, None]:
    """Deploy a test app and return its info, clean up after test."""
    app_name = f"e2e-test-{int(time.time())}"
    deployed = {
        "name": app_name,
        "dir": test_app_dir,
        "deployed": False,
    }

    yield deployed

    # Cleanup: destroy app if it was deployed
    if deployed.get("deployed"):
        subprocess.run(
            ["hop3", "destroy", app_name],
            check=False,
            capture_output=True,
        )
        # Wait for cleanup
        time.sleep(2)


def hop3(
    *args: str, check: bool = True, timeout: int = 60
) -> subprocess.CompletedProcess:
    """Run hop3-cli command and return result.

    Args:
        *args: Command arguments (e.g., "apps", "deploy", "myapp")
        check: If True, raise exception on non-zero exit code
        timeout: Command timeout in seconds (default 60)

    Returns:
        CompletedProcess with stdout, stderr, and returncode
    """
    print(f"Running: hop3 {' '.join(args)}")

    # Debug: check if token is set
    token = os.environ.get("HOP3_API_TOKEN")
    if token:
        print(f"Token is set (first 20 chars): {token[:20]}...")
    else:
        print("WARNING: HOP3_API_TOKEN not set!")

    try:
        result = subprocess.run(
            ["hop3", *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=os.environ.copy(),  # Explicitly pass environment
        )
    except subprocess.TimeoutExpired:
        print(f"Command timed out after {timeout} seconds")
        raise

    print(f"Exit code: {result.returncode}")

    if check and result.returncode != 0:
        print(f"stderr: {result.stderr[:200]}")
        raise subprocess.CalledProcessError(
            result.returncode,
            ["hop3", *args],
            result.stdout,
            result.stderr,
        )

    return result


def wait_for_app_in_list(app_name: str, timeout: int = 30) -> bool:
    """Poll 'hop3 apps' until app appears in list.

    Args:
        app_name: Name of the app to look for
        timeout: Maximum wait time in seconds

    Returns:
        True if app found, False if timeout
    """
    print(f"Waiting for app '{app_name}' to appear in apps list...")
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            result = hop3("apps", check=False)
            if result.returncode == 0 and app_name in result.stdout:
                print(f"✓ App '{app_name}' found in apps list")
                return True
        except Exception as e:
            print(f"  Warning: Error checking apps list: {e}")

        time.sleep(1)

    print(f"✗ Timeout waiting for app '{app_name}' in apps list")
    return False


def create_simple_flask_app(app_dir: Path, app_name: str) -> None:
    """Create a simple Flask app for testing.

    Args:
        app_dir: Directory to create app in
        app_name: Name of the app
    """
    # Create Procfile
    procfile = app_dir / "Procfile"
    procfile.write_text("wsgi: app:app\n")

    # Create app.py
    app_py = app_dir / "app.py"
    app_py.write_text(f"""# Simple Flask app for E2E testing
from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "Hello from {app_name}!"

if __name__ == "__main__":
    app.run()
""")

    # Create requirements.txt
    requirements = app_dir / "requirements.txt"
    requirements.write_text("flask\n")
