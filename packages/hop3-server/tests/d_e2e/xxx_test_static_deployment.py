# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""E2E tests for static file deployment."""

from __future__ import annotations

import base64
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pytest
from hop3_cli.client import Client
from hop3_cli.config import Config

if TYPE_CHECKING:
    from typing import Any


@pytest.mark.e2e
class TestStaticFileDeployment:
    """Test deploying static file applications."""

    def test_deploy_simple_static_app(
        self, hop3_container: dict[str, Any], hop3_command, test_app_dir: Path
    ):
        """Test deploying a simple static HTML application."""
        app_name = f"static-test-{int(time.time())}"

        # Create static HTML files
        (test_app_dir / "index.html").write_text(
            """<!DOCTYPE html>
<html>
<head>
    <title>Static Test</title>
</head>
<body>
    <h1>Hello from Static E2E Test!</h1>
    <p>This is a static file deployment test.</p>
</body>
</html>
"""
        )

        (test_app_dir / "about.html").write_text(
            """<!DOCTYPE html>
<html>
<head>
    <title>About</title>
</head>
<body>
    <h1>About Page</h1>
    <p>This is a static about page.</p>
</body>
</html>
"""
        )

        # Create CSS file
        css_dir = test_app_dir / "css"
        css_dir.mkdir()
        (css_dir / "style.css").write_text(
            """body {
    font-family: Arial, sans-serif;
    margin: 20px;
}
h1 {
    color: #333;
}
"""
        )

        # Create Procfile for static app
        (test_app_dir / "Procfile").write_text("static: .\n")

        # Configure nginx virtual host
        hostname = f"{app_name}.test.local"
        (test_app_dir / "env").write_text(f"NGINX_SERVER_NAME={hostname}\n")

        # Initialize git repo
        subprocess.run(
            ["git", "init"], cwd=test_app_dir, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "add", "."], cwd=test_app_dir, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=test_app_dir,
            check=True,
            capture_output=True,
        )

        # Deploy using git-hook command
        print(f"\nDeploying static app: {app_name}")

        # Get the commit hash
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=test_app_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        commit_hash = result.stdout.strip()

        # Create gzip-compressed tarball from git
        tarball_path = f"/tmp/{app_name}.tar.gz"
        subprocess.run(
            ["git", "archive", "--format=tar.gz", "-o", tarball_path, "HEAD"],
            cwd=test_app_dir,
            check=True,
            capture_output=True,
        )

        # Read tarball and base64 encode it for the deploy command
        tarball_bytes = Path(tarball_path).read_bytes()
        repository_b64 = base64.b64encode(tarball_bytes).decode("utf-8")

        # Deploy via hop3 Client (which uses RPC with kwargs support)
        print(f"Deploying {app_name} via RPC...")
        ssh_key = hop3_container["ssh_key"]
        ssh_port = hop3_container["ssh_port"]

        # Create client with environment config
        # Note: Must use api_url_override to bypass HOP3_API_URL environment variable
        ssh_api_url = f"ssh://hop3@localhost:{ssh_port}"
        env_config = {
            "ssh_key": ssh_key,
        }
        config = Config(data=env_config)
        client = Client(config=config, state=None, api_url_override=ssh_api_url)

        try:
            # Call deploy via RPC
            response = client.rpc(
                "cli", ["deploy", app_name], repository=repository_b64
            )
            print(f"Deploy response: {response}")
        finally:
            # Explicitly close the tunnel to prevent hanging
            if client.tunnel:
                client.tunnel.stop()
                client.tunnel = None

        # Wait for deployment to complete (static apps should be fast)
        print("Waiting for deployment to complete...")
        time.sleep(5)

        # Check app is listed
        result = hop3_command("apps")
        assert result.returncode == 0, f"Failed to list apps: {result.stderr}"
        assert app_name in result.stdout, f"App {app_name} not found in apps list"

        # Check app is running
        result = hop3_command("app:status", app_name)
        assert result.returncode == 0, f"Failed to get status: {result.stderr}"
        assert "RUNNING" in result.stdout or "running" in result.stdout.lower()

        # Test HTTP endpoint via nginx virtual host
        # Get HTTP port from container
        http_port = hop3_container["http_base"].split(":")[-1]
        hostname = f"{app_name}.test.local"

        print(f"Testing HTTP access on port {http_port} with Host: {hostname}")

        # Test with Host header (virtual host routing)
        max_attempts = 10
        attempt = 0
        last_error = None

        while attempt < max_attempts:
            try:
                response = httpx.get(
                    f"http://localhost:{http_port}/",
                    headers={"Host": hostname},
                    timeout=2.0,
                )
                print(f"HTTP Response: {response.status_code}")

                if response.status_code == 200:
                    print(f"Content: {response.text[:100]}")
                    assert "Hello from Static E2E Test" in response.text
                    print(f"✓ HTTP access working via virtual host {hostname}")
                    break
                # Unexpected status code
                print(f"  Unexpected status code: {response.status_code}")
                pytest.fail(f"Unexpected status code: {response.status_code}")
            except (httpx.HTTPError, httpx.ConnectError) as e:
                last_error = e
                print(f"  Attempt {attempt + 1}/{max_attempts}: Connection error: {e}")
                time.sleep(1)
                attempt += 1
        else:
            # Max attempts reached
            print(f"✗ HTTP test failed after {max_attempts} attempts")
            if last_error:
                print(f"Last error: {last_error}")
            pytest.fail(f"HTTP test failed: {last_error}")

        # Test CSS file access
        response = httpx.get(
            f"http://localhost:{http_port}/css/style.css",
            headers={"Host": hostname},
            timeout=2.0,
        )
        assert response.status_code == 200
        assert "font-family" in response.text
        print("✓ CSS file accessible")

        # Test about page
        response = httpx.get(
            f"http://localhost:{http_port}/about.html",
            headers={"Host": hostname},
            timeout=2.0,
        )
        assert response.status_code == 200
        assert "About Page" in response.text
        print("✓ About page accessible")

        print(f"✓ Static app {app_name} deployed successfully")

        # Cleanup
        result = hop3_command("app:destroy", app_name)
        assert result.returncode == 0, f"Failed to destroy app: {result.stderr}"
