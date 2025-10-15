# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""E2E tests for proxy plugin system (Nginx, Caddy, Traefik)."""

from __future__ import annotations

import base64
import os
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

import docker
import httpx
import pytest
from hop3_cli.client import Client
from hop3_cli.config import Config

if TYPE_CHECKING:
    from collections.abc import Generator


def create_proxy_container(
    docker_client: docker.DockerClient, hop3_image: str, proxy_type: str
) -> Generator[dict, None, None]:
    """Create a hop3 container with specific proxy type configured.

    Args:
        docker_client: Docker client instance
        hop3_image: Docker image tag
        proxy_type: Proxy type ("nginx", "caddy", "traefik")

    Yields:
        Container info dict with connection details
    """
    print(f"\n{'=' * 60}")
    print(f"Starting hop3 E2E container with {proxy_type.upper()} proxy")
    print(f"{'=' * 60}")

    # Start container with HOP3_PROXY_TYPE environment variable
    container = docker_client.containers.run(
        hop3_image,
        detach=True,
        environment={
            "HOP3_PROXY_TYPE": proxy_type,
        },
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
            container.reload()
            if container.status != "running":
                print(f"\n❌ Container exited during startup: {container.status}")
                print("Container logs:")
                print(container.logs().decode())
                pytest.fail("Container stopped unexpectedly")

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
            print("\n⚠ hop3-server did not start in time")
            print("\nContainer logs:")
            print(container.logs().decode())
            pytest.fail("hop3-server failed to start")

        # Get container info
        container.reload()
        ports = container.attrs["NetworkSettings"]["Ports"]

        ssh_port = ports["22/tcp"][0]["HostPort"]
        http_port = ports["80/tcp"][0]["HostPort"]
        api_port = ports["8000/tcp"][0]["HostPort"]

        # Get SSH key
        ssh_key_result = container.exec_run("cat /home/hop3/.ssh/id_rsa")
        ssh_key = ssh_key_result.output.decode()

        # Save SSH key
        ssh_key_path = Path("/tmp") / f"hop3-e2e-key-{proxy_type}-{container.short_id}"
        ssh_key_path.write_text(ssh_key)
        ssh_key_path.chmod(0o600)

        container_info = {
            "container": container,
            "proxy_type": proxy_type,
            "ssh_host": "hop3@localhost",
            "ssh_port": int(ssh_port),
            "ssh_key": str(ssh_key_path),
            "http_base": f"http://localhost:{http_port}",
            "http_port": http_port,
            "api_url": f"http://localhost:{api_port}",
        }

        print(f"\nContainer ready with {proxy_type.upper()} proxy:")
        print(f"  SSH: ssh -i {ssh_key_path} -p {ssh_port} hop3@localhost")
        print(f"  HTTP: {container_info['http_base']}")
        print(f"  API: {container_info['api_url']}")
        print(f"{'=' * 60}\n")

        yield container_info

    finally:
        # Cleanup
        print(f"\nStopping {proxy_type} container...")
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

        print(f"{proxy_type.capitalize()} container stopped and removed.")


@pytest.mark.e2e
class TestNginxProxyPlugin:
    """Test Nginx proxy plugin."""

    @pytest.fixture(scope="class")
    def proxy_container(
        self, docker_client: docker.DockerClient, hop3_image: str
    ) -> Generator[dict, None, None]:
        """Create container with Nginx proxy."""
        yield from create_proxy_container(docker_client, hop3_image, "nginx")

    def test_nginx_proxy_deployment(self, proxy_container: dict, test_app_dir: Path):
        """Test deploying an app with Nginx proxy."""
        self._test_proxy_deployment(proxy_container, test_app_dir)

    def _test_proxy_deployment(self, container_info: dict, test_app_dir: Path):
        """Common test logic for proxy deployment."""
        proxy_type = container_info["proxy_type"]
        app_name = f"proxy-test-{proxy_type}-{int(time.time())}"

        # Create simple Flask app
        (test_app_dir / "app.py").write_text(
            f"""
from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "Hello from {proxy_type.upper()} proxy!"

@app.route("/proxy-info")
def proxy_info():
    return {{"proxy": "{proxy_type}", "app": "{app_name}"}}
"""
        )

        (test_app_dir / "requirements.txt").write_text("flask>=3.0\n")

        # Note: Don't use 'cd' in Procfile - uwsgi config sets chdir automatically
        (test_app_dir / "Procfile").write_text(
            "web: flask --app app run --host 0.0.0.0 --port $PORT\n"
        )

        # Configure virtual host
        # IMPORTANT: Environment file must be named "ENV" (uppercase), not "env"
        # Each proxy type uses its own environment variable name
        hostname = f"{app_name}.test.local"
        server_name_var = f"{proxy_type.upper()}_SERVER_NAME"
        (test_app_dir / "ENV").write_text(f"{server_name_var}={hostname}\n")

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

        # Create tarball
        tarball_path = f"/tmp/{app_name}.tar.gz"
        subprocess.run(
            ["git", "archive", "--format=tar.gz", "-o", tarball_path, "HEAD"],
            cwd=test_app_dir,
            check=True,
            capture_output=True,
        )

        # Deploy via RPC
        print(f"\nDeploying {app_name} to {proxy_type.upper()} proxy...")
        tarball_bytes = Path(tarball_path).read_bytes()
        repository_b64 = base64.b64encode(tarball_bytes).decode("utf-8")

        ssh_key = container_info["ssh_key"]
        ssh_port = container_info["ssh_port"]

        # IMPORTANT: Unset HOP3_* environment variables to prevent them from overriding config
        # Config.get() checks environment variables first, so we need to clear them for E2E tests
        old_api_url = os.environ.pop("HOP3_API_URL", None)
        old_ssh_key_env = os.environ.pop("HOP3_SSH_KEY", None)

        try:
            env_config = {
                "api_url": f"ssh://hop3@localhost:{ssh_port}",
                "ssh_key": ssh_key,
            }
            config = Config(data=env_config)
            client = Client(config=config, state=None)

            response = client.rpc(
                "cli", ["deploy", app_name], repository=repository_b64
            )
            print(f"Deploy response: {response}")
        finally:
            # Restore environment variables
            if old_api_url:
                os.environ["HOP3_API_URL"] = old_api_url
            if old_ssh_key_env:
                os.environ["HOP3_SSH_KEY"] = old_ssh_key_env

            if client.tunnel:
                client.tunnel.stop()
                client.tunnel = None

        # Wait for deployment
        print(f"Waiting for {proxy_type} proxy configuration...")
        time.sleep(15)

        # Verify deployment
        print(f"Testing HTTP access through {proxy_type.upper()} proxy...")
        http_port = container_info["http_port"]

        max_attempts = 30
        attempt = 0
        last_error = None

        while attempt < max_attempts:
            try:
                response = httpx.get(
                    f"http://localhost:{http_port}/",
                    headers={"Host": hostname},
                    timeout=2.0,
                )
                print(f"  HTTP Response: {response.status_code}")

                if response.status_code == 200:
                    print(f"  Content: {response.text[:100]}")
                    assert f"Hello from {proxy_type.upper()} proxy" in response.text
                    print(f"✓ {proxy_type.upper()} proxy routing working correctly")
                    break
                if response.status_code == 502:
                    time.sleep(1)
                    attempt += 1
                    continue
                print(f"  Unexpected status code: {response.status_code}")
                pytest.fail(f"Unexpected status code: {response.status_code}")

            except (httpx.HTTPError, httpx.ConnectError) as e:
                last_error = e
                # print(f"  Attempt {attempt + 1}/{max_attempts}: Connection error: {e}")
                time.sleep(1)
                attempt += 1
        else:
            print(
                f"✗ {proxy_type.upper()} proxy test failed after {max_attempts} attempts"
            )
            if last_error:
                print(f"Last error: {last_error}")
            pytest.fail(f"{proxy_type.upper()} proxy did not route traffic correctly")

        print(f"✓ {proxy_type.upper()} proxy plugin test passed")

        # Cleanup
        print(f"Cleaning up {app_name}...")
        # Use container exec for cleanup to avoid SSH tunnel issues
        container = container_info["container"]
        container.exec_run(
            f"su - hop3 -c '~/venv/bin/hop-server app:destroy {app_name}'",
            user="root",
        )


@pytest.mark.e2e
class TestCaddyProxyPlugin:
    """Test Caddy proxy plugin."""

    @pytest.fixture(scope="class")
    def proxy_container(
        self, docker_client: docker.DockerClient, hop3_image: str
    ) -> Generator[dict, None, None]:
        """Create container with Caddy proxy."""
        yield from create_proxy_container(docker_client, hop3_image, "caddy")

    def test_caddy_proxy_deployment(self, proxy_container: dict, test_app_dir: Path):
        """Test deploying an app with Caddy proxy."""
        # Reuse the same test logic
        TestNginxProxyPlugin()._test_proxy_deployment(proxy_container, test_app_dir)


@pytest.mark.e2e
class TestTraefikProxyPlugin:
    """Test Traefik proxy plugin."""

    @pytest.fixture(scope="class")
    def proxy_container(
        self, docker_client: docker.DockerClient, hop3_image: str
    ) -> Generator[dict, None, None]:
        """Create container with Traefik proxy."""
        yield from create_proxy_container(docker_client, hop3_image, "traefik")

    def test_traefik_proxy_deployment(self, proxy_container: dict, test_app_dir: Path):
        """Test deploying an app with Traefik proxy."""
        # Reuse the same test logic
        TestNginxProxyPlugin()._test_proxy_deployment(proxy_container, test_app_dir)
