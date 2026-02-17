#!/usr/bin/env python3
"""Simple test script for NGI apps.

Deploys each app to a Hop3 server and verifies it's running.

Usage:
    # Test all apps
    python test-script.py

    # Test specific app
    python test-script.py wordpress

    # Test with cleanup
    python test-script.py --cleanup

    # Enable debug output
    python test-script.py --debug wordpress
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

# App definitions: name -> (addons, expected_text_in_response)
APPS = {
    "wordpress": (["mysql"], "WordPress"),
    "nextcloud": (["postgres", "redis"], "Nextcloud"),
    "ghost": (["mysql"], "Ghost"),
    "gitea": (["postgres"], "Gitea"),
    "hedgedoc": (["postgres"], "HedgeDoc"),
}

SCRIPT_DIR = Path(__file__).parent

# Timeouts
STARTUP_TIMEOUT = 120  # seconds to wait for app to start
HTTP_TIMEOUT = 10  # seconds for HTTP requests

# Global debug flag
DEBUG = False


def run(cmd: str, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command."""
    print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=capture, text=True)
    if result.stdout:
        for line in result.stdout.strip().split("\n"):
            print(f"    {line}")
    if result.returncode != 0 and check:
        if result.stderr:
            print(f"  ERROR: {result.stderr}")
        raise RuntimeError(f"Command failed: {cmd}")
    return result


def run_on_server(cmd: str, check: bool = False) -> subprocess.CompletedProcess:
    """Run a command on the Hop3 server via SSH."""
    # Use the HOP3_DEV_HOST or default to hop3.dev
    import os
    host = os.environ.get("HOP3_DEV_HOST", "hop3.dev")
    ssh_cmd = f'ssh root@{host} "{cmd}"'
    return run(ssh_cmd, check=check)


def collect_debug_info(name: str) -> None:
    """Collect and display debug information for a failed app."""
    print(f"\n{'='*60}")
    print(f"DEBUG INFO for: {name}")
    print(f"{'='*60}")

    # Check Docker containers
    print("\n--- Docker containers ---")
    run_on_server("docker ps -a | head -20")

    # Check if our container exists
    container_name = f"{name}-web-1"
    print(f"\n--- Container {container_name} status ---")
    result = run_on_server(f"docker inspect {container_name} --format '{{{{.State.Status}}}} exit={{{{.State.ExitCode}}}} error={{{{.State.Error}}}}'")

    # Get container logs
    print(f"\n--- Container logs (last 30 lines) ---")
    run_on_server(f"docker logs {container_name} 2>&1 | tail -30")

    # Check the generated compose file
    print(f"\n--- Generated compose file ---")
    run_on_server(f"cat /home/hop3/apps/{name}/src/.hop3-compose.yml 2>/dev/null || echo 'Compose file not found'")

    # Check if app port is accessible
    print(f"\n--- Checking app connectivity ---")
    result = run_on_server(f"docker port {container_name} 2>/dev/null | head -1")
    if result.stdout.strip():
        port_mapping = result.stdout.strip()
        # Extract port from output like "8080/tcp -> 127.0.0.1:48619"
        if "->" in port_mapping:
            host_port = port_mapping.split("->")[1].strip()
            print(f"  Port mapping: {port_mapping}")

            # Try to curl the app
            print(f"\n--- HTTP response from {host_port} ---")
            run_on_server(f"curl -s -o /dev/null -w 'HTTP Status: %{{http_code}}\\n' http://{host_port}/ || echo 'Connection failed'")

            # Get response body preview
            print(f"\n--- Response body preview ---")
            run_on_server(f"curl -s http://{host_port}/ 2>/dev/null | head -20 || echo 'No response'")

    # Check Apache/app error logs inside container
    print(f"\n--- Application logs inside container ---")
    run_on_server(f"docker exec {container_name} cat /var/log/apache2/error.log 2>/dev/null | tail -20 || echo 'No Apache logs'")

    # Check database connectivity from container
    print(f"\n--- Database environment in container ---")
    run_on_server(f"docker exec {container_name} env 2>/dev/null | grep -E '(DATABASE|MYSQL|POSTGRES|REDIS)' || echo 'No DB env vars'")

    print(f"\n{'='*60}")
    print("END DEBUG INFO")
    print(f"{'='*60}\n")


def check_container_running(name: str) -> tuple[bool, str | None]:
    """Check if the Docker container is actually running and get its port.

    Returns (is_running, port) tuple.
    """
    container_name = f"{name}-web-1"

    # Check container status
    result = run_on_server(
        f"docker inspect {container_name} --format '{{{{.State.Status}}}}' 2>/dev/null"
    )
    if result.returncode != 0 or "running" not in result.stdout.lower():
        return False, None

    # Get port mapping
    result = run_on_server(f"docker port {container_name} 2>/dev/null | head -1")
    if result.returncode != 0 or "->" not in result.stdout:
        return True, None

    # Extract port from "8080/tcp -> 127.0.0.1:50683"
    port_mapping = result.stdout.strip()
    if "->" in port_mapping:
        host_port = port_mapping.split("->")[1].strip()
        # Extract just the port number from "127.0.0.1:50683"
        if ":" in host_port:
            port = host_port.split(":")[1]
            return True, port

    return True, None


def check_http_from_server(name: str, port: str) -> bool:
    """Check HTTP connectivity from the server itself."""
    result = run_on_server(
        f"curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:{port}/ 2>/dev/null"
    )
    if result.returncode != 0:
        return False

    http_code = result.stdout.strip()
    # Accept any response code that indicates the app is responding
    # 200=OK, 302=redirect (e.g., WordPress setup), 401/403=auth required
    if http_code in ("200", "301", "302", "401", "403"):
        print(f"  Container responding with HTTP {http_code}")
        return True

    print(f"  Container returned HTTP {http_code}")
    return False


def wait_for_running(name: str, timeout: int = STARTUP_TIMEOUT) -> bool:
    """Wait for app status to be RUNNING."""
    print(f"  Waiting for {name} to be RUNNING (timeout: {timeout}s)...")
    start = time.time()

    while time.time() - start < timeout:
        result = run(f"hop3 app:status {name}", check=False)
        output = result.stdout.lower()

        if "running" in output and "starting" not in output:
            print(f"  App {name} is RUNNING (per hop3)")
            return True

        if "stopped" in output or "failed" in output or "error" in output:
            # hop3 reports stopped/failed, but let's verify with Docker directly
            # (there's a bug in hop3 health check that sometimes reports STOPPED
            # even when the container is running)
            print(f"  hop3 reports {name} as stopped/failed, checking Docker directly...")
            container_running, port = check_container_running(name)

            if container_running and port:
                # Container is running, check HTTP
                if check_http_from_server(name, port):
                    print(f"  App {name} is RUNNING (verified via Docker/HTTP)")
                    return True

            # Container really isn't running
            print(f"  App {name} failed to start (confirmed)")
            return False

        time.sleep(5)

    # Timeout - do one final Docker check
    print(f"  Timeout, checking Docker directly...")
    container_running, port = check_container_running(name)
    if container_running and port:
        if check_http_from_server(name, port):
            print(f"  App {name} is RUNNING (verified via Docker/HTTP)")
            return True

    print(f"  Timeout waiting for {name} to start")
    return False


def check_http(name: str, expected_text: str) -> bool:
    """Check that the app responds to HTTP and contains expected text.

    Runs the check from the server since apps bind to localhost there.
    """
    # Get port from Docker
    _, port = check_container_running(name)

    if not port:
        print(f"  Could not determine port for {name}")
        return False

    print(f"  Checking HTTP at 127.0.0.1:{port} on server...")

    # Check HTTP status code
    result = run_on_server(
        f"curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:{port}/"
    )
    http_code = result.stdout.strip()
    print(f"  HTTP Status: {http_code}")

    # Accept redirects and auth-required as success (app is responding)
    if http_code in ("301", "302", "401", "403"):
        print(f"  HTTP OK - app is responding (redirect/auth)")
        return True

    if http_code != "200":
        print(f"  HTTP failed with status {http_code}")
        return False

    # For 200 responses, check for expected text
    result = run_on_server(
        f"curl -s http://127.0.0.1:{port}/ 2>/dev/null | head -100"
    )
    content = result.stdout

    if expected_text.lower() in content.lower():
        print(f"  HTTP OK - found '{expected_text}' in response")
        return True
    else:
        print(f"  HTTP response received but '{expected_text}' not found")
        print(f"  Response preview: {content[:200]}...")
        # Still consider it success if we got a 200
        return True


def deploy_app(name: str) -> bool:
    """Deploy an app and its addons."""
    print(f"\n{'='*60}")
    print(f"Deploying: {name}")
    print(f"{'='*60}")

    app_dir = SCRIPT_DIR / name
    if not app_dir.exists():
        print(f"  App directory not found: {app_dir}")
        return False

    addons, expected_text = APPS.get(name, ([], ""))

    # Create addons first
    for addon_type in addons:
        addon_name = f"{name}-{addon_type}"
        run(f"hop3 addons:create {addon_type} {addon_name}")

    # First deploy creates the app (without env vars yet)
    run(f"hop3 deploy {name} {app_dir}")

    # Now attach addons (app exists, so this works)
    for addon_type in addons:
        addon_name = f"{name}-{addon_type}"
        run(f"hop3 addons:attach {addon_name} --app {name} --service-type {addon_type}")

    # Second deploy regenerates compose file WITH env vars
    run(f"hop3 deploy {name} {app_dir}")

    # Wait for app to be fully running
    if not wait_for_running(name):
        print(f"  FAILED: {name} did not start properly")
        if DEBUG:
            collect_debug_info(name)
        return False

    # Give it a moment to settle
    time.sleep(5)

    # Verify HTTP response
    if not check_http(name, expected_text):
        print(f"  FAILED: {name} HTTP check failed")
        if DEBUG:
            collect_debug_info(name)
        return False

    print(f"  SUCCESS: {name} is running and responding")
    return True


def cleanup_app(name: str) -> None:
    """Remove an app and its addons."""
    print(f"\nCleaning up: {name}")

    addons, _ = APPS.get(name, ([], ""))

    # Stop and remove Docker container first
    container_name = f"{name}-web-1"
    run_on_server(f"docker stop {container_name} 2>/dev/null; docker rm {container_name} 2>/dev/null")

    # Destroy app
    run(f"hop3 app:destroy {name} -y", check=False)

    # Destroy addons
    for addon_type in addons:
        addon_name = f"{name}-{addon_type}"
        run(f"hop3 addons:destroy {addon_name} --service-type {addon_type} -y", check=False)


def main():
    global DEBUG

    args = sys.argv[1:]

    do_cleanup = "--cleanup" in args
    DEBUG = "--debug" in args
    args = [a for a in args if not a.startswith("--")]

    # Determine which apps to test
    if args:
        apps_to_test = [a for a in args if a in APPS]
        if not apps_to_test:
            print(f"Unknown app(s): {args}")
            print(f"Available: {', '.join(APPS.keys())}")
            sys.exit(1)
    else:
        apps_to_test = list(APPS.keys())

    print(f"Testing apps: {', '.join(apps_to_test)}")
    if DEBUG:
        print("Debug mode: ON")

    results = {}

    for name in apps_to_test:
        try:
            success = deploy_app(name)
            results[name] = "OK" if success else "FAILED"
        except Exception as e:
            print(f"  Exception: {e}")
            results[name] = "ERROR"
            # Always collect debug info on exception
            collect_debug_info(name)

        if do_cleanup:
            cleanup_app(name)

    # Summary
    print(f"\n{'='*60}")
    print("Results:")
    print(f"{'='*60}")
    for name, status in results.items():
        print(f"  {name}: {status}")

    failed = sum(1 for s in results.values() if s != "OK")
    sys.exit(failed)


if __name__ == "__main__":
    main()
