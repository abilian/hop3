# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Common application management routines for demos."""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

from lib.commands import run_hop3
from lib.logging import timed
from lib.output import (
    cyan,
    dim,
    get_output_level,
    green,
    pause,
    print_error,
    print_header,
    print_info,
    print_step,
    print_success,
    yellow,
)

if TYPE_CHECKING:
    from lib.context import DemoContext


def ensure_app_removed(app_name: str) -> None:
    """Ensure an app doesn't exist before deploying.

    Args:
        app_name: Name of the application to remove if it exists
    """
    # Try to destroy the app, ignoring errors if it doesn't exist
    run_hop3(f"app destroy --app {app_name} -y", check=False, show=False, quiet=True)
    # Wait for uwsgi emperor to fully clean up the process
    # Longer delay helps prevent race conditions with gunicorn workers
    time.sleep(5)


def deploy_app(ctx: DemoContext, app_name: str, app_dir: Path) -> None:
    """Deploy an application from a directory.

    Args:
        ctx: Demo context
        app_name: Name of the application
        app_dir: Path to the application directory
    """
    # Ensure clean state by removing any existing app
    ensure_app_removed(app_name)

    print_step(f"Deploying {app_name} application...")
    with timed(f"deploy {app_name}", category="deploy"):
        # cwd=app_dir: deploy is the one demo command that needs a project in
        # its CWD (the CLI reads the app dir there). Everything else runs from a
        # hermetic dir (see run_hop3). --force: demos deploy a shared app
        # template under a demo-specific name (e.g. "demo01"), which need not
        # match the app's [metadata].id ("hello-hop3"). --force tells the CLI
        # "yes, deploy the resolved --app here" — bypassing the project-id
        # mismatch guard — and also implies skip-confirm (so the non-interactive
        # demo doesn't block on the deploy prompt). See core/project_guard.py.
        run_hop3(f"deploy --app {app_name} --force", cwd=str(app_dir))
    print_success("Application deployed")
    pause(ctx.pause_between_steps)


def set_hostname(ctx: DemoContext, app_name: str, hostname: str) -> None:
    """Set the hostname for an application.

    Args:
        ctx: Demo context
        app_name: Name of the application
        hostname: Hostname to set
    """
    print_step(f"Configuring hostname: {hostname}")
    run_hop3(f"config set --app {app_name} HOST_NAME={hostname}")
    print_success(f"Hostname set to {hostname}")
    pause(ctx.pause_between_steps)


def redeploy_app(ctx: DemoContext, app_name: str, app_dir: Path) -> None:
    """Redeploy an application to apply configuration changes.

    Args:
        ctx: Demo context
        app_name: Name of the application
        app_dir: Path to the application directory
    """
    print_step("Redeploying to apply configuration...")

    # Wait a moment before redeploy to avoid race conditions with uwsgi emperor
    time.sleep(2)

    # Simply redeploy - the app already exists with its config
    # DeployCmd handles existing apps by retrieving them, preserving env_vars
    with timed(f"redeploy {app_name}", category="deploy"):
        # cwd=app_dir + --force: see deploy_app.
        run_hop3(f"deploy --app {app_name} --force", cwd=str(app_dir))

    print_success("Application redeployed")
    pause(ctx.pause_between_steps)


def _get_app_config(app_name: str) -> dict[str, str]:
    """Get current config for an app.

    Returns:
        Dict of config key-value pairs.
    """
    result = run_hop3(f"config show --app {app_name}", check=False, show=False, quiet=True)
    config = {}
    if result.returncode == 0 and result.stdout:
        lines = result.stdout.strip().split("\n")
        # Skip header line and separator line (tabulate format)
        # Format: "Key    Value\n-----  ------\nKEY1   val1\n..."
        data_started = False
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # Skip header and separator lines
            if stripped.startswith(("Key", "-")):
                data_started = True
                continue
            if not data_started:
                continue
            # Parse table row: split on 2+ spaces (tabulate column separator)
            parts = re.split(r"\s{2,}", stripped, maxsplit=1)
            if len(parts) == 2:
                key, value = parts
                if key and not key.startswith("#"):
                    config[key] = value
    return config


def _restore_app_config(app_name: str, config: dict[str, str]) -> None:
    """Restore config to an app.

    Args:
        app_name: Name of the application
        config: Dict of config key-value pairs
    """
    for key, value in config.items():
        run_hop3(f"config set --app {app_name} {key}={value}", show=False, quiet=True)


def wait_for_app(
    seconds: int = 5, message: str = "Waiting for application to start..."
) -> None:
    """Wait for an application to start (legacy fixed wait).

    DEPRECATED: Use wait_for_app_ready() for smart polling instead.

    Args:
        seconds: Number of seconds to wait
        message: Message to display
    """
    from lib.logging import record_timing

    print_step(message)
    time.sleep(seconds)
    record_timing(f"wait {seconds}s (fixed)", seconds, category="wait")


def wait_for_app_ready(
    app_name: str,
    timeout: float = 30.0,
    poll_interval: float = 0.5,
    message: str | None = None,
) -> bool:
    """Poll until application is ready.

    Uses hop3 app ping to check if the app is responding.
    Much faster than fixed waits when app starts quickly.

    Args:
        app_name: Name of the application
        timeout: Maximum time to wait in seconds
        poll_interval: Time between polls in seconds
        message: Optional message to display

    Returns:
        True if app is ready, False if timeout reached
    """
    from lib.logging import record_timing

    if message:
        print_step(message)
    else:
        print_step(f"Waiting for {app_name} to be ready...")

    start = time.time()
    attempts = 0

    while time.time() - start < timeout:
        attempts += 1
        result = run_hop3(f"app ping --app {app_name}", check=False, show=False, quiet=True)
        if result.returncode == 0:
            elapsed = time.time() - start
            record_timing(
                f"wait ready ({attempts} polls, {elapsed:.1f}s)",
                elapsed,
                category="wait",
            )
            print_success(f"Application ready after {elapsed:.1f}s")
            return True
        time.sleep(poll_interval)

    elapsed = time.time() - start
    record_timing(
        f"wait timeout ({attempts} polls, {elapsed:.1f}s)", elapsed, category="wait"
    )
    print_error(f"Application not ready after {timeout}s")
    return False


def check_app_status(ctx: DemoContext, app_name: str) -> None:
    """Check and display application status.

    Args:
        ctx: Demo context
        app_name: Name of the application
    """
    print_step("Checking application status...")
    run_hop3(f"app status --app {app_name}")
    print_success("Application is running")
    pause(ctx.pause_between_steps)


def test_app_via_curl(
    ctx: DemoContext,
    app_url: str,
    expected_content: str,
    max_retries: int = 10,
    retry_delay: float = 2.0,
) -> None:
    """Test application accessibility via curl with retries.

    Args:
        ctx: Demo context
        app_url: URL to test
        expected_content: Content expected in response
        max_retries: Maximum number of retry attempts
        retry_delay: Seconds to wait between retries

    Raises:
        RuntimeError: If application is not accessible or content doesn't match
    """
    from lib.logging import record_timing

    curl_start = time.time()
    print_step(f"Verifying external access via {app_url}...")

    # Extract hostname from URL and use --resolve for DNS resolution
    # This allows testing with custom hostnames like "myapp.hop"
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(app_url)
    hostname = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    # For Docker mode, use the mapped ports (10443 for HTTPS, 10080 for HTTP)
    if ctx.backend == "docker":
        backend = ctx.get_backend()
        if parsed.scheme == "https":
            port = getattr(backend, "port_https", 10443)
        else:
            port = getattr(backend, "port_http", 10080)
        # Update URL with the mapped port
        app_url = f"{parsed.scheme}://{hostname}:{port}{parsed.path or '/'}"

    # Resolve server IP if it's a hostname (--resolve requires actual IP address)
    server_ip = ctx.server_ip
    try:
        # Check if server_ip is already an IP address
        socket.inet_aton(server_ip)
    except OSError:
        # It's a hostname, resolve it
        try:
            server_ip = socket.gethostbyname(server_ip)
        except socket.gaierror:
            pass  # Keep original if resolution fails

    # Build curl command with --resolve to map hostname to server IP
    # -L follows redirects (important for apps that redirect to /login, /install, etc.)
    # --max-time 10 prevents hanging on unresponsive backends
    resolve_opt = f"--resolve {hostname}:{port}:{server_ip}" if hostname else ""
    curl_cmd = f"curl -skL --max-time 10 {resolve_opt} {app_url}"

    last_result = None
    for attempt in range(max_retries):
        result = subprocess.run(
            curl_cmd, shell=True, capture_output=True, text=True, check=False
        )
        last_result = result

        if result.returncode == 0 and expected_content in result.stdout:
            if get_output_level() >= 2:  # NORMAL or VERBOSE
                print(f"  {green('Response:')}")
                print(f"  {result.stdout.strip()}")
                print()
            record_timing(
                f"curl test ({attempt + 1} attempts)",
                time.time() - curl_start,
                category="curl",
            )
            print_success(f"Application accessible at {app_url}")
            pause(ctx.pause_between_steps)
            return

        # Check if we got a 502/504 Bad Gateway or 404 (app may still be starting)
        if any(
            err in result.stdout
            for err in ["502 Bad Gateway", "504 Gateway", "404 Not Found"]
        ) or "Connection refused" in str(result.stderr):
            if attempt < max_retries - 1:
                print_info(
                    f"  App not ready yet, retrying in {retry_delay}s... ({attempt + 1}/{max_retries})"
                )
                time.sleep(retry_delay)
                continue

        # Got a different error, fail immediately
        break

    # Determine if it's a connection issue or content mismatch (needed for the
    # raised message regardless of output level).
    if last_result and last_result.returncode == 0 and last_result.stdout:
        error_type = "content_mismatch"
    else:
        error_type = "connection_error"

    # Inline diagnostics at NORMAL+ only; in quiet/silent this ~40-line dump
    # would land mid-line and shred the per-demo result line. The full detail is
    # logged via log_section below and the failure surfaces in the run summary.
    if get_output_level() >= 2:  # NORMAL or VERBOSE
        if error_type == "content_mismatch":
            print_error(f"Content validation failed for {app_url}")
            print(f"  {yellow('Expected:')} '{expected_content}'")
            print(f"  {yellow('Actual response:')} ({len(last_result.stdout)} bytes)")
            # Show more of the response for debugging
            print(f"  {last_result.stdout[:500].strip()}")
        else:
            print_error(f"Failed to access application at {app_url}")
            print(f"  {yellow('Expected:')} '{expected_content}'")
            if last_result and last_result.stdout:
                print(f"  {yellow('Got response:')} ({len(last_result.stdout)} bytes)")
                print(f"  {last_result.stdout[:500].strip()}")

        print(f"  {yellow('Curl command:')} {curl_cmd}")
        if last_result:
            print(f"  {yellow('Exit code:')} {last_result.returncode}")
            if last_result.stderr:
                print(f"  {yellow('Stderr:')}")
                print(f"  {last_result.stderr[:200].strip()}")

        # Try to get app logs for debugging
        # Extract app name from URL (e.g., demo13.hop3.dev -> demo13)
        app_name_from_url = hostname.split(".")[0] if hostname else None
        if app_name_from_url:
            print_info(f"  Fetching logs for '{app_name_from_url}'...")
            logs_result = run_hop3(
                f"app logs --app {app_name_from_url} --lines 50",
                check=False,
                show=False,
                quiet=True,
            )
            if logs_result.returncode == 0 and logs_result.stdout:
                print(f"  {yellow('Recent app logs:')}")
                for line in logs_result.stdout.strip().split("\n")[-30:]:
                    print(f"    {line}")
            else:
                print_info("  (No logs available or app not found)")

    # Log curl details to file for debugging
    from lib.logging import log_section

    log_section(
        "curl-test",
        f"Curl test failed for {app_url}",
        f"Command: {curl_cmd}\n"
        f"Expected: {expected_content}\n"
        f"Exit code: {last_result.returncode if last_result else 'N/A'}\n"
        f"Response ({len(last_result.stdout) if last_result and last_result.stdout else 0} bytes):\n"
        f"{last_result.stdout[:1000] if last_result and last_result.stdout else 'N/A'}\n"
        f"Stderr: {last_result.stderr if last_result and last_result.stderr else 'N/A'}",
    )

    record_timing(
        f"curl test FAILED ({max_retries} attempts)",
        time.time() - curl_start,
        category="curl",
    )

    if error_type == "content_mismatch":
        msg = f"Content validation failed at {app_url}: expected '{expected_content}' not found in response"
    else:
        msg = f"Application not accessible at {app_url}"
    raise RuntimeError(msg)


def curl_request(ctx: DemoContext, url: str) -> subprocess.CompletedProcess:
    """Make a curl request with proper DNS resolution.

    Uses --resolve to map the hostname to the server IP, allowing
    requests to custom hostnames like "demo32.hop3.dev".

    Args:
        ctx: Demo context
        url: URL to request

    Returns:
        CompletedProcess with stdout, stderr, and returncode
    """
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(url)
    hostname = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    # For Docker mode, use the mapped ports
    if ctx.backend == "docker":
        backend = ctx.get_backend()
        if parsed.scheme == "https":
            port = getattr(backend, "port_https", 10443)
        else:
            port = getattr(backend, "port_http", 10080)
        # Update URL with the mapped port
        url = f"{parsed.scheme}://{hostname}:{port}{parsed.path or '/'}"

    # Resolve server IP if it's a hostname
    server_ip = ctx.server_ip
    try:
        socket.inet_aton(server_ip)
    except OSError:
        try:
            server_ip = socket.gethostbyname(server_ip)
        except socket.gaierror:
            pass

    # Build curl command with --resolve
    # --max-time 10 prevents hanging on unresponsive backends
    resolve_opt = f"--resolve {hostname}:{port}:{server_ip}" if hostname else ""
    curl_cmd = f"curl -sk --max-time 10 {resolve_opt} {url}"

    return subprocess.run(
        curl_cmd, shell=True, capture_output=True, text=True, check=False
    )


def test_app_via_hop3(
    ctx: DemoContext,
    app_name: str,
    app_url: str,
    *,
    is_static: bool = False,
) -> None:
    """Test application using hop3 app ping command.

    Args:
        ctx: Demo context
        app_name: Name of the application
        app_url: URL for display purposes
        is_static: If True, skip app ping (static apps have no backend port)
    """
    print_step(f"Testing the application via HTTPS at {app_url}...")
    print_info("Using curl with -k flag to accept self-signed certificate.")
    if is_static:
        print_info("Static app - skipping internal ping (served directly by nginx).")
    else:
        run_hop3(f"app ping --app {app_name}", check=False)
    pause(ctx.pause_between_steps)


def list_apps(ctx: DemoContext) -> None:
    """List all deployed applications.

    Args:
        ctx: Demo context
    """
    print_step("Listing all deployed applications...")
    run_hop3("apps")
    pause(ctx.pause_between_steps)


def show_config(ctx: DemoContext, app_name: str) -> None:
    """Show application configuration/environment variables.

    Args:
        ctx: Demo context
        app_name: Name of the application
    """
    print_step("Viewing environment variables...")
    run_hop3(f"config show --app {app_name}")
    pause(ctx.pause_between_steps)


def set_env_vars(ctx: DemoContext, app_name: str, **env_vars: str) -> None:
    """Set environment variables for an application.

    Args:
        ctx: Demo context
        app_name: Name of the application
        **env_vars: Environment variables to set
    """
    print_step("Setting environment variables...")
    vars_str = " ".join(f"{k}={v}" for k, v in env_vars.items())
    run_hop3(f"config set --app {app_name} {vars_str}")
    pause(ctx.pause_between_steps)


def restart_app(ctx: DemoContext, app_name: str, wait_seconds: int = 2) -> None:
    """Restart an application and wait.

    Args:
        ctx: Demo context
        app_name: Name of the application
        wait_seconds: Seconds to wait after restart
    """
    print_step("Restarting application...")
    run_hop3(f"app restart --app {app_name}")
    time.sleep(wait_seconds)
    print_success("Application restarted")
    pause(ctx.pause_between_steps)


def cleanup_app(ctx: DemoContext, app_name: str, app_url: str) -> None:
    """Cleanup/destroy an application if cleanup is enabled.

    Args:
        ctx: Demo context
        app_name: Name of the application
        app_url: URL for display when skipping cleanup
    """
    if not ctx.no_cleanup:
        print_header("Cleanup")
        print_step(f"Destroying the {app_name} application...")
        with timed(f"destroy {app_name}", category="cleanup"):
            run_hop3(f"app destroy --app {app_name} -y")
        print_success("Application destroyed")
        # Wait briefly to ensure uwsgi emperor has fully cleaned up the process
        time.sleep(1)
    else:
        print_info(f"Skipping cleanup. App running at {app_url}")


def show_file_content(
    file_path: Path,
    title: str,
    max_lines: int | None = None,
) -> None:
    """Display the content of a file.

    Args:
        file_path: Path to the file
        title: Title to display
        max_lines: Maximum lines to show (None for all)
    """
    if get_output_level() < 2:  # SILENT or QUIET
        return

    print_step(title)
    if file_path.exists():
        print()
        content = file_path.read_text()
        lines = content.split("\n")
        if max_lines:
            lines = lines[:max_lines]
        for line in lines:
            print(f"  {dim(line)}")
        print()


def show_app_structure(app_name: str, files: list[tuple[str, str]]) -> None:
    """Display the application directory structure.

    Args:
        app_name: Name of the application directory
        files: List of (filename, description) tuples
    """
    if get_output_level() < 2:  # SILENT or QUIET
        return

    print_step("Application structure:")
    print()
    print(f"  {cyan(app_name + '/')}")
    for i, (filename, description) in enumerate(files):
        prefix = "+--" if i == len(files) - 1 else "|--"
        print(f"  {prefix} {green(filename)} - {description}")
    print()
