# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Pytest fixtures for end-to-end tests using hop3-cli binary.

This module provides fixtures for E2E testing that:
- Use the hop3-cli binary exclusively (no direct SSH)
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
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

# Get server from environment (required for E2E tests)
E2E_SERVER = os.environ.get("HOP3_DEV_HOST")
E2E_TEST_USER = "e2e-test-user"
E2E_TEST_EMAIL = "e2e-test@example.com"
E2E_TEST_PASSWORD = "e2e-test-password-12345"


@pytest.fixture(scope="session")
def e2e_enabled() -> bool:
    """Check if E2E tests are enabled."""
    if not E2E_SERVER:
        pytest.skip("E2E tests require HOP3_DEV_HOST environment variable")

    print("\n=== E2E Test Setup ===")
    print(f"Server: {E2E_SERVER}")
    print(f"Test user: {E2E_TEST_USER}")

    return True


@pytest.fixture(scope="session")
def hop3_config_dir(e2e_enabled) -> Generator[Path, None, None]:
    """Set up hop3-cli configuration via environment variables."""
    config_dir = Path(tempfile.mkdtemp(prefix="hop3-e2e-config-"))

    # Set API URL via environment variable (hop3-cli checks HOP3_API_URL)
    original_api_url = os.environ.get("HOP3_API_URL")
    api_url = f"ssh://{E2E_SERVER}"
    os.environ["HOP3_API_URL"] = api_url

    print("\n=== Configuration ===")
    print(f"API URL: {api_url}")
    print(f"Config dir: {config_dir}")

    yield config_dir

    # Cleanup
    if config_dir.exists():
        shutil.rmtree(config_dir)

    # Restore original environment
    if original_api_url:
        os.environ["HOP3_API_URL"] = original_api_url
    else:
        os.environ.pop("HOP3_API_URL", None)


@pytest.fixture(scope="session")
def e2e_auth_token(hop3_config_dir: Path) -> Generator[str, None, None]:
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
        pytest.fail(
            "Registration command timed out after 30 seconds. Check SSH connection."
        )

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
        pytest.fail("Login command timed out after 30 seconds. Check SSH connection.")

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

    # Extract token from output
    # Format is:
    # Login successful for user: {username}
    #
    # Your API token:
    # {token}
    # ...
    token = None
    lines = result.stdout.split("\n")
    for i, line in enumerate(lines):
        if "Your API token:" in line:
            # Token is on the next line
            if i + 1 < len(lines):
                token = lines[i + 1].strip()
                break

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
        pytest.fail(debug_info)

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
    except subprocess.TimeoutExpired as e:
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
