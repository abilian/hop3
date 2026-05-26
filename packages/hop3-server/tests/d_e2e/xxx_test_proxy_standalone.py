#!/usr/bin/env python3
# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Standalone test script for proxy plugins - easier debugging than pytest."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import docker
import docker.errors
import httpx


def main():  # noqa: PLR0911 — standalone scratch driver (xxx_ prefix → not collected by pytest); each early return is a distinct setup-step failure printed for the human running it ad-hoc.
    """Run standalone proxy plugin test."""
    proxy_type = sys.argv[1] if len(sys.argv) > 1 else "nginx"

    print(f"\n{'=' * 70}")
    print(f"Standalone Proxy Plugin Test: {proxy_type.upper()}")
    print(f"{'=' * 70}\n")

    # Get Docker client
    docker_client = docker.from_env()
    docker_client.ping()
    print("✓ Docker connected\n")

    # Build or get image
    image_tag = "hop3-e2e:test"
    try:
        docker_client.images.get(image_tag)
        print(f"✓ Using existing image: {image_tag}\n")
    except docker.errors.ImageNotFound:
        print(f"✗ Image {image_tag} not found. Please build it first.")
        print(
            f"  Run: docker build -f packages/hop3-server/tests/d_e2e/docker/Dockerfile -t {image_tag} ."
        )
        return 1

    # Start container
    print(f"Starting container with {proxy_type.upper()} proxy...")
    container = docker_client.containers.run(
        image_tag,
        detach=True,
        environment={
            "HOP3_PROXY_TYPE": proxy_type,
        },
        ports={
            "22/tcp": None,
            "80/tcp": None,
            "8000/tcp": None,
        },
    )

    try:  # noqa: PLW0717 — standalone scratch driver (xxx_ prefix → not collected). The 130-statement body is a monolithic end-to-end probe (deploy, inspect logs, curl); a refactor belongs at the level of "promote this to a real test suite", not the try-block.
        container_id = container.short_id
        print(f"✓ Container started: {container_id}\n")

        # Wait for services
        print("Waiting for services to initialize...")
        time.sleep(5)

        container.reload()
        if container.status != "running":
            print(f"✗ Container exited with status: {container.status}")
            print("\nContainer logs:")
            print(container.logs().decode())
            return 1

        # Wait for hop3-server
        print("Waiting for hop3-server to respond...")
        for i in range(30):
            container.reload()
            if container.status != "running":
                print(f"✗ Container stopped: {container.status}")
                return 1

            try:
                result = container.exec_run(
                    "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/"
                )
                if b"200" in result.output or b"404" in result.output:
                    print("✓ hop3-server is responding\n")
                    break
            except Exception as e:
                print(f"  Attempt {i + 1}/30: {e}")

            time.sleep(2)
        else:
            print("✗ hop3-server did not start in time")
            return 1

        # Get ports
        container.reload()
        ports = container.attrs["NetworkSettings"]["Ports"]
        ssh_port = int(ports["22/tcp"][0]["HostPort"])
        http_port = int(ports["80/tcp"][0]["HostPort"])
        api_port = int(ports["8000/tcp"][0]["HostPort"])

        print("Container ports:")
        print(f"  SSH:  {ssh_port}")
        print(f"  HTTP: {http_port}")
        print(f"  API:  {api_port}\n")

        # Get SSH key
        ssh_key_result = container.exec_run("cat /home/hop3/.ssh/id_rsa")
        ssh_key = ssh_key_result.output.decode()
        ssh_key_path = Path(f"/tmp/hop3-test-key-{container_id}")
        ssh_key_path.write_text(ssh_key)
        ssh_key_path.chmod(0o600)

        # Create test app
        app_name = f"proxy-test-{proxy_type}-{int(time.time())}"
        hostname = f"{app_name}.test.local"

        test_dir = Path(f"/tmp/{app_name}")
        test_dir.mkdir(exist_ok=True)

        print(f"Creating test app: {app_name}")
        print(f"Hostname: {hostname}\n")

        # Create Flask app
        (test_dir / "app.py").write_text(f"""
from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "Hello from {proxy_type.upper()} proxy!"
""")

        (test_dir / "requirements.txt").write_text("flask>=3.0\n")
        # Note: Don't use 'cd' in Procfile - uwsgi config sets chdir automatically
        (test_dir / "Procfile").write_text(
            "web: flask --app app run --host 0.0.0.0 --port $PORT\n"
        )
        # IMPORTANT: Environment file must be named "ENV" (uppercase), not "env"
        # Each proxy type uses its own environment variable name
        server_name_var = f"{proxy_type.upper()}_SERVER_NAME"
        (test_dir / "ENV").write_text(f"{server_name_var}={hostname}\n")

        # Create git repo
        subprocess.run(["git", "init"], cwd=test_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "add", "."], cwd=test_dir, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=test_dir,
            check=True,
            capture_output=True,
        )

        # Create tarball
        tarball_path = f"/tmp/{app_name}.tar.gz"
        subprocess.run(
            ["git", "archive", "--format=tar.gz", "-o", tarball_path, "HEAD"],
            cwd=test_dir,
            check=True,
            capture_output=True,
        )

        # Deploy via hop3 CLI
        print("Deploying app...")

        # Set environment for hop3 CLI
        env = os.environ.copy()
        env["HOP3_API_URL"] = f"ssh://hop3@localhost:{ssh_port}"
        env["HOP3_SSH_KEY"] = str(ssh_key_path)
        env["HOP3_SECRET_KEY"] = "e2e-test-secret-key-do-not-use-in-production"

        # Deploy using hop3 CLI with tarball as stdin
        with Path(tarball_path).open("rb") as f:
            result = subprocess.run(
                ["hop3", "deploy", app_name],
                stdin=f,
                capture_output=True,
                check=False,
                text=True,
                env=env,
                timeout=60,
            )

        if result.returncode != 0:
            print(
                f"✗ Deployment failed (exit code {result.returncode}): {result.stderr}"
            )
        else:
            print(f"✓ Deploy succeeded: {result.stdout}\n")

        # Check hop3-server logs to see what happened during deployment
        print("Checking hop3-server logs...")
        result = container.exec_run("tail -100 /var/log/supervisor/hop3-server.log")
        if result.exit_code == 0:
            print("=== hop3-server.log (last 100 lines) ===")
            print(result.output.decode())
        else:
            print(f"✗ Could not read hop3-server logs: {result.output.decode()}")

        # Check nginx status and config
        print("\nChecking nginx status in container...")
        result = container.exec_run("supervisorctl status nginx")
        print(f"Nginx status: {result.output.decode()}")

        print("\nChecking nginx config files...")
        result = container.exec_run("ls -la /home/hop3/nginx/")
        print(f"Nginx configs: {result.output.decode()}")

        result = container.exec_run(f"cat /home/hop3/nginx/{app_name}.conf")
        if result.exit_code == 0:
            print(f"\nNginx config for {app_name}:")
            print(result.output.decode()[:500])
        else:
            print(f"✗ Could not read nginx config: {result.output.decode()}")

        # Check nginx error log
        print("\nChecking nginx error log...")
        result = container.exec_run("tail -20 /var/log/nginx/error.log")
        if result.exit_code == 0:
            print(result.output.decode())

        # Check uwsgi status
        print("\nChecking uwsgi status...")
        result = container.exec_run("supervisorctl status uwsgi")
        print(f"uwsgi status: {result.output.decode()}")

        # Check uwsgi logs
        print("\nChecking uwsgi logs...")
        result = container.exec_run("tail -50 /var/log/supervisor/uwsgi.log")
        if result.exit_code == 0:
            print("=== uwsgi.log (last 50 lines) ===")
            print(result.output.decode())

        # Check if the app's uwsgi config exists
        print(f"\nChecking uwsgi config for {app_name}...")
        result = container.exec_run("ls -la /home/hop3/uwsgi-enabled/")
        print(f"uwsgi-enabled dir: {result.output.decode()}")

        result = container.exec_run(
            f"cat /home/hop3/uwsgi-enabled/{app_name}_web.1.ini"
        )
        if result.exit_code == 0:
            print(f"\nuwsgi config for {app_name}:")
            print(result.output.decode())
        else:
            print(f"✗ Could not read uwsgi config: {result.output.decode()}")

        # Wait for deployment
        print(f"\nWaiting 15 seconds for {proxy_type} to settle...")
        time.sleep(15)

        # Test HTTP access
        print(f"\nTesting HTTP access on port {http_port} with Host: {hostname}...")

        for attempt in range(30):
            try:
                response = httpx.get(
                    f"http://localhost:{http_port}/",
                    headers={"Host": hostname},
                    timeout=2.0,
                )
                print(f"  Attempt {attempt + 1}: HTTP {response.status_code}")

                if response.status_code == 200:
                    print("\n✓ SUCCESS!")
                    print(f"  Response: {response.text[:100]}")
                    if f"Hello from {proxy_type.upper()} proxy" in response.text:
                        print(f"\n{'=' * 70}")
                        print(f"✓ {proxy_type.upper()} PROXY TEST PASSED!")
                        print(f"{'=' * 70}\n")
                        return 0
                    print("✗ Unexpected response content")
                    return 1
                if response.status_code == 502:
                    print("    Backend not ready (502)")
                else:
                    print(f"    Unexpected status: {response.status_code}")

            except Exception as e:
                print(f"  Attempt {attempt + 1}: {type(e).__name__}: {e}")

            time.sleep(1)

        print("\n✗ Test failed after 30 attempts")

        # Final debugging
        print("\nFinal debugging info:")
        result = container.exec_run("ps aux | grep nginx")
        print(f"Nginx processes:\n{result.output.decode()}")

        result = container.exec_run("netstat -tlnp | grep :80")
        print(f"\nPort 80 listeners:\n{result.output.decode()}")

        print(f"\nContainer ID: {container.id}")
        print(f"To inspect: docker exec -it {container.id} bash")
        print("To keep running, press Ctrl+C and container will remain")

        input("\nPress Enter to stop container and exit...")

        return 1

    finally:
        # Cleanup
        print("\nCleaning up...")
        try:
            container.stop(timeout=10)
            container.remove(force=True)
            print("✓ Container removed")
        except Exception as e:
            print(f"Warning: {e}")

        if ssh_key_path.exists():
            ssh_key_path.unlink()
            print("✓ SSH key removed")


if __name__ == "__main__":
    sys.exit(main())
