#!/usr/bin/env python3
"""Test script for NGI apps.

Deploys apps to a Hop3 server and verifies they're running.

Usage:
    # Test specific app
    python test-script.py docker-based/wordpress

    # Test all apps in a directory
    python test-script.py "docker-based/*"

    # Test multiple apps
    python test-script.py docker-based/wordpress docker-based/ghost

    # Test with cleanup
    python test-script.py --cleanup docker-based/wordpress

    # Enable debug output
    python test-script.py --debug docker-based/wordpress
"""

from __future__ import annotations

import glob
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

SCRIPT_DIR = Path(__file__).parent

# Timeouts
STARTUP_TIMEOUT = 120  # seconds to wait for app to start
HTTP_TIMEOUT = 10  # seconds for HTTP requests

# Global debug flag
DEBUG = False


@dataclass
class AppConfig:
    """App configuration parsed from hop3.toml."""

    name: str
    path: Path
    addons: list[str]
    env_vars: dict[str, str]
    title: str = ""
    healthcheck_path: str = "/"

    @classmethod
    def from_path(cls, app_path: Path) -> "AppConfig":
        """Parse app configuration from hop3.toml."""
        toml_path = app_path / "hop3.toml"
        if not toml_path.exists():
            raise ValueError(f"No hop3.toml found in {app_path}")

        with open(toml_path, "rb") as f:
            config = tomllib.load(f)

        # Extract metadata
        metadata = config.get("metadata", {})
        name = metadata.get("id", app_path.name)
        title = metadata.get("title", name)

        # Extract addons
        addons = []
        for addon in config.get("addons", []):
            addon_type = addon.get("type")
            if addon_type:
                addons.append(addon_type)

        # Extract env vars
        env_vars = config.get("env", {})

        # Extract healthcheck
        healthcheck = config.get("healthcheck", {})
        healthcheck_path = healthcheck.get("path", "/")

        return cls(
            name=name,
            path=app_path,
            addons=addons,
            env_vars=env_vars,
            title=title,
            healthcheck_path=healthcheck_path,
        )


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


def run_streaming(cmd: str, check: bool = True) -> int:
    """Run a shell command with streaming output (for long-running commands)."""
    print(f"  $ {cmd}")
    process = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    for line in process.stdout:
        print(f"    {line.rstrip()}")
    process.wait()
    if process.returncode != 0 and check:
        raise RuntimeError(f"Command failed: {cmd}")
    return process.returncode


def run_on_server(cmd: str, check: bool = False) -> subprocess.CompletedProcess:
    """Run a command on the Hop3 server via SSH."""
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
    run_on_server(
        f"docker inspect {container_name} --format "
        "'{{{{.State.Status}}}} exit={{{{.State.ExitCode}}}} error={{{{.State.Error}}}}'"
    )

    # Get container logs
    print(f"\n--- Container logs (last 30 lines) ---")
    run_on_server(f"docker logs {container_name} 2>&1 | tail -30")

    # Check the generated compose file
    print(f"\n--- Generated compose file ---")
    run_on_server(
        f"cat /home/hop3/apps/{name}/src/.hop3-compose.yml 2>/dev/null || echo 'Compose file not found'"
    )

    # Check if app port is accessible
    print(f"\n--- Checking app connectivity ---")
    result = run_on_server(f"docker port {container_name} 2>/dev/null | head -1")
    if result.stdout.strip():
        port_mapping = result.stdout.strip()
        if "->" in port_mapping:
            host_port = port_mapping.split("->")[1].strip()
            print(f"  Port mapping: {port_mapping}")

            print(f"\n--- HTTP response from {host_port} ---")
            run_on_server(
                f"curl -s -o /dev/null -w 'HTTP Status: %{{http_code}}\\n' "
                f"http://{host_port}/ || echo 'Connection failed'"
            )

            print(f"\n--- Response body preview ---")
            run_on_server(f"curl -s http://{host_port}/ 2>/dev/null | head -20 || echo 'No response'")

    # Check Apache/app error logs inside container
    print(f"\n--- Application logs inside container ---")
    run_on_server(
        f"docker exec {container_name} cat /var/log/apache2/error.log 2>/dev/null | tail -20 "
        "|| echo 'No Apache logs'"
    )

    # Check database connectivity from container
    print(f"\n--- Database environment in container ---")
    run_on_server(
        f"docker exec {container_name} env 2>/dev/null | "
        "grep -E '(DATABASE|MYSQL|POSTGRES|REDIS|PG)' || echo 'No DB env vars'"
    )

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
            # Verify with Docker directly (workaround for hop3 status bug)
            print(f"  hop3 reports {name} as stopped/failed, checking Docker directly...")
            container_running, port = check_container_running(name)

            if container_running and port:
                if check_http_from_server(name, port):
                    print(f"  App {name} is RUNNING (verified via Docker/HTTP)")
                    return True

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


def check_http(name: str) -> bool:
    """Check that the app responds to HTTP.

    Runs the check from the server since apps bind to localhost there.
    """
    _, port = check_container_running(name)

    if not port:
        print(f"  Could not determine port for {name}")
        return False

    print(f"  Checking HTTP at 127.0.0.1:{port} on server...")

    result = run_on_server(
        f"curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:{port}/"
    )
    http_code = result.stdout.strip()
    print(f"  HTTP Status: {http_code}")

    # Accept redirects and auth-required as success
    if http_code in ("200", "301", "302", "401", "403"):
        print(f"  HTTP OK - app is responding")
        return True

    print(f"  HTTP failed with status {http_code}")
    return False


def deploy_app(app: AppConfig) -> bool:
    """Deploy an app.

    Addons and env vars are now handled automatically by hop3 deploy
    based on the [[addons]] and [env] sections in hop3.toml.
    """
    print(f"\n{'='*60}")
    print(f"Deploying: {app.title} ({app.name})")
    print(f"  Path: {app.path}")
    print(f"  Addons (from config): {app.addons}")
    if app.env_vars:
        print(f"  Env vars (from config): {list(app.env_vars.keys())}")
    print(f"{'='*60}")

    if not app.path.exists():
        print(f"  App directory not found: {app.path}")
        return False

    # Single deploy - addons and env vars are processed automatically from hop3.toml
    # Use streaming output so user can see progress during long builds
    run_streaming(f"hop3 deploy {app.name} {app.path}")

    # Wait for app to be fully running
    if not wait_for_running(app.name):
        print(f"  FAILED: {app.name} did not start properly")
        if DEBUG:
            collect_debug_info(app.name)
        return False

    # Give it a moment to settle
    time.sleep(5)

    # Verify HTTP response
    if not check_http(app.name):
        print(f"  FAILED: {app.name} HTTP check failed")
        if DEBUG:
            collect_debug_info(app.name)
        return False

    print(f"  SUCCESS: {app.name} is running and responding")
    return True


def cleanup_app(app: AppConfig) -> None:
    """Remove an app and its addons."""
    print(f"\nCleaning up: {app.name}")

    # Stop and remove Docker container first
    container_name = f"{app.name}-web-1"
    run_on_server(f"docker stop {container_name} 2>/dev/null; docker rm {container_name} 2>/dev/null")

    # Destroy app
    run(f"hop3 app:destroy {app.name} -y", check=False)

    # Destroy addons
    for addon_type in app.addons:
        addon_name = f"{app.name}-{addon_type}"
        run(f"hop3 addons:destroy {addon_name} --service-type {addon_type} -y", check=False)


def expand_app_paths(patterns: list[str]) -> list[Path]:
    """Expand glob patterns to app paths."""
    paths = []
    for pattern in patterns:
        # Handle glob patterns
        if "*" in pattern:
            full_pattern = str(SCRIPT_DIR / pattern)
            matches = glob.glob(full_pattern)
            for match in sorted(matches):
                match_path = Path(match)
                # Only include directories with hop3.toml
                if match_path.is_dir() and (match_path / "hop3.toml").exists():
                    paths.append(match_path)
        else:
            # Direct path
            app_path = SCRIPT_DIR / pattern
            if app_path.is_dir():
                paths.append(app_path)
            else:
                print(f"Warning: {pattern} is not a valid directory")
    return paths


def main():
    global DEBUG

    args = sys.argv[1:]

    do_cleanup = "--cleanup" in args
    DEBUG = "--debug" in args
    args = [a for a in args if not a.startswith("--")]

    # Default to docker-based/* if no args
    if not args:
        args = ["docker-based/*"]

    # Expand paths
    app_paths = expand_app_paths(args)

    if not app_paths:
        print(f"No apps found matching: {args}")
        print(f"Available apps in docker-based/:")
        for p in sorted((SCRIPT_DIR / "docker-based").glob("*")):
            if p.is_dir() and (p / "hop3.toml").exists():
                print(f"  docker-based/{p.name}")
        sys.exit(1)

    # Parse app configs
    apps: list[AppConfig] = []
    for path in app_paths:
        try:
            app = AppConfig.from_path(path)
            apps.append(app)
        except Exception as e:
            print(f"Error parsing {path}: {e}")
            sys.exit(1)

    print(f"Testing {len(apps)} app(s): {', '.join(a.name for a in apps)}")
    if DEBUG:
        print("Debug mode: ON")

    results = {}

    for app in apps:
        try:
            success = deploy_app(app)
            results[app.name] = "OK" if success else "FAILED"
        except Exception as e:
            print(f"  Exception: {e}")
            results[app.name] = "ERROR"
            collect_debug_info(app.name)

        if do_cleanup:
            cleanup_app(app)

    # Summary
    print(f"\n{'='*60}")
    print("Results:")
    print(f"{'='*60}")
    for name, status in results.items():
        symbol = "+" if status == "OK" else "-"
        print(f"  [{symbol}] {name}: {status}")

    failed = sum(1 for s in results.values() if s != "OK")
    print(f"\nTotal: {len(results) - failed}/{len(results)} passed")
    sys.exit(failed)


if __name__ == "__main__":
    main()
