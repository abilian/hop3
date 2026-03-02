#!/usr/bin/env python3
"""Test script for packaged apps.

Deploys apps to a Hop3 server and verifies they're running.

Usage:
    # Test specific app
    python test-script.py docker-apps/wordpress

    # Test all apps in a directory
    python test-script.py "docker-apps/*"

    # Test multiple apps
    python test-script.py docker-apps/wordpress docker-apps/ghost

    # Test native apps
    python test-script.py "native-apps/*"

    # Test with cleanup
    python test-script.py --cleanup docker-apps/wordpress

    # Enable debug output
    python test-script.py --debug docker-apps/wordpress
"""

from __future__ import annotations

import glob
import io
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

SCRIPT_DIR = Path(__file__).parent
LOGS_DIR = SCRIPT_DIR / "logs"

# Timeouts
STARTUP_TIMEOUT = 120  # seconds to wait for app to start
HTTP_TIMEOUT = 10  # seconds for HTTP requests

# Global debug flag
DEBUG = False

# Current log file (set per-app)
CURRENT_LOG_FILE: io.TextIOWrapper | None = None


def log_print(*args, **kwargs):
    """Print to both console and current log file if set."""
    print(*args, **kwargs)
    if CURRENT_LOG_FILE:
        # Also write to log file
        output = io.StringIO()
        print(*args, **kwargs, file=output)
        CURRENT_LOG_FILE.write(output.getvalue())
        CURRENT_LOG_FILE.flush()


@dataclass
class AppConfig:
    """App configuration parsed from hop3.toml."""

    name: str
    path: Path
    addons: list[str]
    env_vars: dict[str, str]
    title: str = ""
    healthcheck_path: str = "/"
    deployment_type: str = "docker"  # "docker" or "native"

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

        # Determine deployment type from [build] section
        # builder = "local" means native/uWSGI deployment
        # Otherwise (no builder or builder = "docker") means Docker deployment
        build_config = config.get("build", {})
        builder = build_config.get("builder", "")
        deployment_type = "native" if builder == "local" else "docker"

        return cls(
            name=name,
            path=app_path,
            addons=addons,
            env_vars=env_vars,
            title=title,
            healthcheck_path=healthcheck_path,
            deployment_type=deployment_type,
        )


def run(cmd: str, check: bool = True, capture: bool = True, quiet: bool = False) -> subprocess.CompletedProcess:
    """Run a shell command.

    Args:
        cmd: Command to run
        check: Raise exception on failure
        capture: Capture output (vs letting it go to terminal)
        quiet: Only show output on failure
    """
    if not quiet:
        log_print(f"  $ {cmd}")

    if capture:
        # Use Popen with communicate() to safely handle large outputs
        process = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = process.communicate()
        result = subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)
    else:
        result = subprocess.run(cmd, shell=True, text=True)

    # Only show output on failure or if not quiet
    if result.returncode != 0 or not quiet:
        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                log_print(f"    {line}")
        if result.stderr and result.returncode != 0:
            log_print(f"  ERROR: {result.stderr}")

    if result.returncode != 0 and check:
        raise RuntimeError(f"Command failed: {cmd}")

    return result


def run_streaming(cmd: str, check: bool = True, timeout: int = 600) -> int:
    """Run a shell command with streaming output (for long-running commands).

    Uses a thread to read output, avoiding blocking issues.
    """
    import threading
    import queue

    log_print(f"  $ {cmd}")

    process = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    output_queue: queue.Queue = queue.Queue()

    def reader_thread():
        """Read lines from process stdout and put them in queue."""
        try:
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                output_queue.put(line)
        except Exception:
            pass
        finally:
            output_queue.put(None)  # Signal EOF

    thread = threading.Thread(target=reader_thread, daemon=True)
    thread.start()

    start_time = time.time()

    while True:
        # Check timeout
        if time.time() - start_time > timeout:
            process.kill()
            log_print(f"    [TIMEOUT after {timeout}s]")
            break

        try:
            line = output_queue.get(timeout=1.0)
            if line is None:
                # EOF reached
                break
            decoded = line.decode("utf-8", errors="replace").rstrip()
            if decoded:
                log_print(f"    {decoded}")
        except queue.Empty:
            # No output available, check if process is still running
            if process.poll() is not None:
                # Process finished, drain any remaining output
                time.sleep(0.1)  # Give thread time to finish
                while True:
                    try:
                        line = output_queue.get_nowait()
                        if line is None:
                            break
                        decoded = line.decode("utf-8", errors="replace").rstrip()
                        if decoded:
                            log_print(f"    {decoded}")
                    except queue.Empty:
                        break
                break

    thread.join(timeout=2.0)
    process.wait()

    if process.returncode != 0 and check:
        raise RuntimeError(f"Command failed: {cmd}")
    return process.returncode


def run_on_server(cmd: str, check: bool = False, quiet: bool = False) -> subprocess.CompletedProcess:
    """Run a command on the Hop3 server via SSH."""
    host = os.environ.get("HOP3_DEV_HOST", "hop3.dev")
    ssh_cmd = f'ssh root@{host} "{cmd}"'
    return run(ssh_cmd, check=check, quiet=quiet)




def collect_debug_info_native(name: str) -> None:
    """Collect debug information for a native/uWSGI app."""
    log_print(f"\n{'='*60}")
    log_print(f"DEBUG INFO for: {name} (native/uWSGI)")
    log_print(f"{'='*60}")

    # Check uWSGI config
    log_print("\n--- uWSGI config ---")
    run_on_server(f"cat /home/hop3/uwsgi-enabled/{name}_web.1.ini 2>/dev/null | head -30 || echo 'Config not found'")

    # Check uWSGI logs
    log_print(f"\n--- uWSGI logs (last 30 lines) ---")
    run_on_server(f"tail -30 /home/hop3/apps/{name}/log/web.1.log 2>/dev/null || echo 'Log not found'")

    # Check app port from config
    log_print(f"\n--- App port configuration ---")
    result = run_on_server(f"grep 'env = PORT=' /home/hop3/uwsgi-enabled/{name}_web.1.ini 2>/dev/null", quiet=True)
    port = None
    if result.returncode == 0 and "PORT=" in result.stdout:
        port = result.stdout.split("PORT=")[1].strip()
        log_print(f"  Configured PORT: {port}")

        # Check HTTP connectivity
        log_print(f"\n--- HTTP connectivity test ---")
        run_on_server(
            f"curl -s -o /dev/null -w 'HTTP Status: %{{http_code}}\\n' "
            f"http://127.0.0.1:{port}/ 2>/dev/null || echo 'Connection failed'"
        )

    # Check if process is running
    log_print(f"\n--- Process status ---")
    run_on_server(f"pgrep -f 'apps/{name}' && echo 'Process found' || echo 'No process running'")

    # Check LIVE_ENV
    log_print(f"\n--- Environment variables (LIVE_ENV) ---")
    run_on_server(f"cat /home/hop3/apps/{name}/venv/LIVE_ENV 2>/dev/null | head -20 || echo 'LIVE_ENV not found'")

    # Check source directory
    log_print(f"\n--- Source directory contents ---")
    run_on_server(f"ls -la /home/hop3/apps/{name}/src/ 2>/dev/null | head -20 || echo 'Source dir not found'")

    log_print(f"\n{'='*60}")
    log_print("END DEBUG INFO")
    log_print(f"{'='*60}\n")


def collect_debug_info_docker(name: str) -> None:
    """Collect debug information for a Docker app."""
    log_print(f"\n{'='*60}")
    log_print(f"DEBUG INFO for: {name} (Docker)")
    log_print(f"{'='*60}")

    # Check Docker containers
    log_print("\n--- Docker containers ---")
    run_on_server("docker ps -a | head -20")

    # Check if our container exists
    container_name = f"{name}-web-1"
    log_print(f"\n--- Container {container_name} status ---")
    run_on_server(
        f"docker inspect {container_name} --format "
        "'{{.State.Status}} exit={{.State.ExitCode}} error={{.State.Error}}' 2>/dev/null || echo 'Container not found'"
    )

    # Get container logs
    log_print(f"\n--- Container logs (last 30 lines) ---")
    run_on_server(f"docker logs {container_name} 2>&1 | tail -30")

    # Check the generated compose file
    log_print(f"\n--- Generated compose file ---")
    run_on_server(
        f"cat /home/hop3/apps/{name}/src/.hop3-compose.yml 2>/dev/null || echo 'Compose file not found'"
    )

    # Check if app port is accessible
    log_print(f"\n--- Checking app connectivity ---")
    result = run_on_server(f"docker port {container_name} 2>/dev/null | head -1")
    if result.stdout.strip():
        port_mapping = result.stdout.strip()
        if "->" in port_mapping:
            host_port = port_mapping.split("->")[1].strip()
            log_print(f"  Port mapping: {port_mapping}")

            log_print(f"\n--- HTTP response from {host_port} ---")
            run_on_server(
                f"curl -s -o /dev/null -w 'HTTP Status: %{{http_code}}\\n' "
                f"http://{host_port}/ || echo 'Connection failed'"
            )

            log_print(f"\n--- Response body preview ---")
            run_on_server(f"curl -s http://{host_port}/ 2>/dev/null | head -20 || echo 'No response'")

    # Check Apache/app error logs inside container
    log_print(f"\n--- Application logs inside container ---")
    run_on_server(
        f"docker exec {container_name} cat /var/log/apache2/error.log 2>/dev/null | tail -20 "
        "|| echo 'No Apache logs'"
    )

    # Check database connectivity from container
    log_print(f"\n--- Database environment in container ---")
    run_on_server(
        f"docker exec {container_name} env 2>/dev/null | "
        "grep -E '(DATABASE|MYSQL|POSTGRES|REDIS|PG)' || echo 'No DB env vars'"
    )

    log_print(f"\n{'='*60}")
    log_print("END DEBUG INFO")
    log_print(f"{'='*60}\n")


def collect_debug_info(name: str, deployment_type: str = "docker") -> None:
    """Collect and display debug information for a failed app.

    Args:
        name: App name
        deployment_type: "docker" or "native" (from AppConfig.deployment_type)
    """
    if deployment_type == "docker":
        collect_debug_info_docker(name)
    else:
        collect_debug_info_native(name)


def check_uwsgi_running(name: str) -> tuple[bool, str | None]:
    """Check if the app is running via uWSGI and get its port.

    Returns (is_running, port) tuple.
    """
    # Check if uWSGI config exists
    config_path = f"/home/hop3/uwsgi-enabled/{name}_web.1.ini"
    result = run_on_server(f"grep 'env = PORT=' {config_path} 2>/dev/null", quiet=True)
    if result.returncode != 0:
        return False, None

    # Extract port from "env = PORT=44057"
    port = None
    for line in result.stdout.strip().split("\n"):
        if "PORT=" in line:
            port = line.split("PORT=")[1].strip()
            break

    if not port:
        return False, None

    # Check if process is running on that port
    result = run_on_server(
        f"curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:{port}/ 2>/dev/null",
        quiet=True
    )
    if result.returncode == 0 and result.stdout.strip() not in ("000", ""):
        return True, port

    return False, port


def check_container_running(name: str) -> tuple[bool, str | None]:
    """Check if the Docker container is actually running and get its port.

    Returns (is_running, port) tuple.
    """
    container_name = f"{name}-web-1"

    # Check container status
    result = run_on_server(
        f"docker inspect {container_name} --format '{{{{.State.Status}}}}' 2>/dev/null",
        quiet=True
    )
    if result.returncode != 0 or "running" not in result.stdout.lower():
        return False, None

    # Get port mapping
    result = run_on_server(f"docker port {container_name} 2>/dev/null | head -1", quiet=True)
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


def check_app_running(name: str, deployment_type: str = "docker") -> tuple[bool, str | None]:
    """Check if the app is running via Docker or uWSGI.

    Args:
        name: App name
        deployment_type: "docker" or "native" (from AppConfig.deployment_type)

    Returns (is_running, port) tuple.
    """
    if deployment_type == "docker":
        return check_container_running(name)
    else:
        # Native/uWSGI deployment
        return check_uwsgi_running(name)


def check_http_from_server(name: str, port: str, quiet: bool = False) -> tuple[bool, str]:
    """Check HTTP connectivity from the server itself.

    Returns (success, http_code) tuple.
    """
    result = run_on_server(
        f"curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:{port}/ 2>/dev/null",
        quiet=True
    )
    if result.returncode != 0:
        return False, "000"

    http_code = result.stdout.strip()
    # Accept any response code that indicates the app is responding
    # 2xx = success, 3xx = redirect, 401/403 = auth required, 400 = API services
    if http_code in ("200", "301", "302", "307", "308", "401", "403", "400"):
        if not quiet:
            log_print(f"  App responding with HTTP {http_code}")
        return True, http_code

    if not quiet:
        log_print(f"  App returned HTTP {http_code}")
    return False, http_code


def wait_for_http_ready(name: str, port: str, timeout: int = 30) -> bool:
    """Wait for app to respond with a healthy HTTP status.

    Some apps (like Laravel) may temporarily return 500/503 during startup
    or when restarting after config changes.
    """
    start = time.time()
    last_code = "000"

    while time.time() - start < timeout:
        success, http_code = check_http_from_server(name, port, quiet=True)
        last_code = http_code

        if success:
            log_print(f"  App responding with HTTP {http_code}")
            return True

        # 500/502/503 means app is starting or restarting - keep waiting
        if http_code in ("500", "502", "503"):
            log_print(f"  App returned HTTP {http_code}, waiting for startup...")
            time.sleep(3)
            continue

        # Other errors (000, 404, etc.) - keep trying but less frequently
        time.sleep(2)

    log_print(f"  HTTP check timed out (last status: {last_code})")
    return False


def wait_for_running(name: str, deployment_type: str = "docker", timeout: int = STARTUP_TIMEOUT) -> bool:
    """Wait for app status to be RUNNING.

    Args:
        name: App name
        deployment_type: "docker" or "native" (from AppConfig.deployment_type)
        timeout: Max seconds to wait
    """
    log_print(f"  Waiting for {name} to be RUNNING (timeout: {timeout}s)...")
    start = time.time()

    while time.time() - start < timeout:
        result = run(f"hop3 app:status {name}", check=False)
        output = result.stdout.lower()

        if "running" in output and "starting" not in output:
            log_print(f"  App {name} is RUNNING (per hop3)")
            return True

        if "stopped" in output or "failed" in output or "error" in output:
            # Verify directly (workaround for hop3 status bug)
            log_print(f"  hop3 reports {name} as stopped/failed, checking directly...")
            is_running, port = check_app_running(name, deployment_type)

            if is_running and port:
                # Give the app time to fully start - some apps restart during init
                remaining_time = max(10, int(timeout - (time.time() - start)))
                if wait_for_http_ready(name, port, timeout=remaining_time):
                    log_print(f"  App {name} is RUNNING (verified via HTTP)")
                    return True

            log_print(f"  App {name} failed to start (confirmed)")
            return False

        time.sleep(5)

    # Timeout - do one final check
    log_print(f"  Timeout, checking directly...")
    is_running, port = check_app_running(name, deployment_type)
    if is_running and port:
        if wait_for_http_ready(name, port, timeout=10):
            log_print(f"  App {name} is RUNNING (verified via HTTP)")
            return True

    log_print(f"  Timeout waiting for {name} to start")
    return False


def check_http(name: str, deployment_type: str = "docker") -> bool:
    """Check that the app responds to HTTP.

    Runs the check from the server since apps bind to localhost there.
    Uses retry logic to handle apps that may be restarting.

    Args:
        name: App name
        deployment_type: "docker" or "native" (from AppConfig.deployment_type)
    """
    _, port = check_app_running(name, deployment_type)

    if not port:
        log_print(f"  Could not determine port for {name}")
        return False

    log_print(f"  Checking HTTP at 127.0.0.1:{port} on server...")

    # Use retry logic - some apps may be restarting
    if wait_for_http_ready(name, port, timeout=15):
        log_print(f"  HTTP OK - app is responding")
        return True

    log_print(f"  HTTP check failed")
    return False


def deploy_app(app: AppConfig) -> bool:
    """Deploy an app.

    Addons and env vars are now handled automatically by hop3 deploy
    based on the [[addons]] and [env] sections in hop3.toml.
    """
    log_print(f"\n{'='*60}")
    log_print(f"Deploying: {app.title} ({app.name})")
    log_print(f"  Path: {app.path}")
    log_print(f"  Type: {app.deployment_type}")
    log_print(f"  Addons (from config): {app.addons}")
    if app.env_vars:
        log_print(f"  Env vars (from config): {list(app.env_vars.keys())}")
    log_print(f"{'='*60}")

    if not app.path.exists():
        log_print(f"  App directory not found: {app.path}")
        return False

    # Single deploy - addons and env vars are processed automatically from hop3.toml
    # Use streaming output so user can see progress during long builds
    run_streaming(f"hop3 deploy {app.name} {app.path}")

    # Wait for app to be fully running
    if not wait_for_running(app.name, app.deployment_type):
        log_print(f"  FAILED: {app.name} did not start properly")
        if DEBUG:
            collect_debug_info(app.name, app.deployment_type)
        return False

    # Give it a moment to settle
    time.sleep(5)

    # Verify HTTP response
    if not check_http(app.name, app.deployment_type):
        log_print(f"  FAILED: {app.name} HTTP check failed")
        if DEBUG:
            collect_debug_info(app.name, app.deployment_type)
        return False

    log_print(f"  SUCCESS: {app.name} is running and responding")
    return True


def cleanup_app(app: AppConfig) -> None:
    """Remove an app and its addons."""
    log_print(f"\nCleaning up: {app.name}")

    if app.deployment_type == "docker":
        # Stop and remove Docker container
        container_name = f"{app.name}-web-1"
        run_on_server(f"docker stop {container_name} 2>/dev/null; docker rm {container_name} 2>/dev/null")

    # Destroy app (works for both Docker and native)
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
                log_print(f"Warning: {pattern} is not a valid directory")
    return paths


def main():
    global DEBUG, CURRENT_LOG_FILE

    args = sys.argv[1:]

    do_cleanup = "--cleanup" in args
    DEBUG = "--debug" in args
    args = [a for a in args if not a.startswith("--")]

    # Default to docker-apps/* if no args
    if not args:
        args = ["docker-apps/*"]

    # Create logs directory
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Expand paths
    app_paths = expand_app_paths(args)

    if not app_paths:
        print(f"No apps found matching: {args}")
        print(f"Available apps in docker-apps/:")
        for p in sorted((SCRIPT_DIR / "docker-apps").glob("*")):
            if p.is_dir() and (p / "hop3.toml").exists():
                print(f"  docker-apps/{p.name}")
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
    print(f"Logs will be saved to: {LOGS_DIR}/")
    if DEBUG:
        print("Debug mode: ON")

    results = {}

    for app in apps:
        # Open log file for this app
        log_file_path = LOGS_DIR / f"{app.name}.log"
        try:
            CURRENT_LOG_FILE = open(log_file_path, "w", encoding="utf-8")
            CURRENT_LOG_FILE.write(f"=== Log for {app.name} ===\n")
            CURRENT_LOG_FILE.write(f"Started at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        except OSError as e:
            print(f"Warning: Could not create log file {log_file_path}: {e}")
            CURRENT_LOG_FILE = None

        try:
            success = deploy_app(app)
            results[app.name] = "OK" if success else "FAILED"
        except Exception as e:
            log_print(f"  Exception: {e}")
            results[app.name] = "ERROR"
            collect_debug_info(app.name, app.deployment_type)

        if do_cleanup:
            cleanup_app(app)

        # Close log file
        if CURRENT_LOG_FILE:
            CURRENT_LOG_FILE.write(f"\n=== End of log for {app.name} ===\n")
            CURRENT_LOG_FILE.write(f"Result: {results[app.name]}\n")
            CURRENT_LOG_FILE.write(f"Ended at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            CURRENT_LOG_FILE.close()
            CURRENT_LOG_FILE = None

    # Summary (to console only)
    print(f"\n{'='*60}")
    print("Results:")
    print(f"{'='*60}")
    for name, status in results.items():
        symbol = "+" if status == "OK" else "-"
        print(f"  [{symbol}] {name}: {status}")

    failed = sum(1 for s in results.values() if s != "OK")
    print(f"\nTotal: {len(results) - failed}/{len(results)} passed")
    print(f"\nLogs saved to: {LOGS_DIR}/")
    sys.exit(failed)


if __name__ == "__main__":
    main()
