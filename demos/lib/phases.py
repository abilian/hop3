# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo execution phases."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

from lib.commands import cli_env, reset_cli_home, run_hop3
from lib.context import DemoResult, OutputLevel
from lib.discovery import load_demo_module
from lib.logging import (
    capture_failure_debug,
    end_demo_logging,
    get_log_session,
    log_section,
    start_demo_logging,
)
from lib.output import (
    dim,
    pause,
    print_command,
    print_error,
    print_failure_detail,
    print_header,
    print_info,
    print_phase_result,
    print_step,
    print_success,
    red,
    yellow,
)

if TYPE_CHECKING:
    from lib.context import DemoContext


def run_prerequisites(ctx: DemoContext) -> bool:
    """Run Phase 1: Prerequisites.

    Args:
        ctx: Demo context

    Returns:
        True on success, False on failure.
    """
    from lib.commands import CommandError
    from lib.logging import record_timing
    from lib.server import (
        check_dns_resolution,
        check_hop3_installed,
        check_ubuntu_version,
        clean_server,
        configure_server_settings,
        install_hop3,
        update_hop3_server,
        verify_connectivity,
    )

    # Skip preflight checks if not requested (faster iteration)
    if not ctx.preflight and ctx.skip_install and not ctx.clean_before:
        print_info("Skipping prerequisites (use --preflight to run checks)")
        return True

    print_header("Checking prerequisites", phase=True)
    phase_start = time.time()

    try:
        # For Docker backend, always set up the container first (regardless of --preflight)
        # This is required because Docker backend needs to create/start the container
        # before any other operations can run.
        if ctx.backend == "docker" and not ctx.preflight:
            from lib.commands import CommandError as CmdError

            backend = ctx.get_backend()
            print_step("Setting up Docker container...")
            step_start = time.time()
            if not backend.setup():
                print_error("Failed to set up Docker container")
                raise CmdError("Docker container setup failed")
            record_timing("docker_setup", time.time() - step_start, category="setup")
            print_success(f"Docker container '{ctx.docker_container}' ready")
            pause(ctx.pause_between_steps)

        # Preflight checks (only with --preflight)
        if ctx.preflight:
            step_start = time.time()
            verify_connectivity(ctx)
            record_timing(
                "verify_connectivity", time.time() - step_start, category="setup"
            )
            pause(ctx.pause_between_steps)

            # For SSH backend, check DNS and Ubuntu version
            if ctx.backend == "ssh":
                # Check DNS resolution for demo hostnames (local check, before server checks)
                step_start = time.time()
                check_dns_resolution(ctx)
                record_timing(
                    "check_dns_resolution", time.time() - step_start, category="setup"
                )
                pause(ctx.pause_between_steps)

                step_start = time.time()
                check_ubuntu_version(ctx)
                record_timing(
                    "check_ubuntu_version", time.time() - step_start, category="setup"
                )
                pause(ctx.pause_between_steps)

        # Clean server if requested (before installation)
        if ctx.clean_before:
            step_start = time.time()
            clean_server(ctx)
            record_timing("clean_server", time.time() - step_start, category="setup")
            pause(ctx.pause_between_steps)

        # Installation checks (skip if --skip-install)
        if not ctx.skip_install:
            step_start = time.time()
            hop3_installed = check_hop3_installed(ctx)
            record_timing(
                "check_hop3_installed", time.time() - step_start, category="setup"
            )

            if not hop3_installed:
                step_start = time.time()
                install_hop3(ctx)
                record_timing(
                    "install_hop3", time.time() - step_start, category="setup"
                )
            else:
                step_start = time.time()
                update_hop3_server(ctx)
                record_timing(
                    "update_hop3_server", time.time() - step_start, category="setup"
                )
        else:
            print_info("Skipping Hop3 installation/update (--skip-install)")

        # Configure server settings (DEBUG logging, Docker hosts) - always run
        pause(ctx.pause_between_steps)
        step_start = time.time()
        configure_server_settings(ctx)
        record_timing(
            "configure_server_settings", time.time() - step_start, category="setup"
        )

        record_timing(
            "prerequisites_phase", time.time() - phase_start, category="phase"
        )
        print_phase_result(success=True)
        pause(ctx.pause_between_steps)
        return True

    except CommandError as e:
        print_phase_result(success=False)
        if ctx.verbose:
            print_error(str(e))
        return False


def _wait_for_http_ready(
    server_url: str, timeout: float = 120.0, interval: float = 2.0
) -> bool:
    """Poll ``server_url`` until it answers HTTP, or ``timeout`` elapses.

    Any HTTP response (including 3xx/4xx — the root redirects to /auth/login,
    and /rpc would 401) means the server is up and accepting connections,
    which is all we need before ``hop3 login``. Connection refused / reset /
    timeout means "not ready yet". Returns True once reachable, else False.
    """
    import urllib.error  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(server_url, timeout=5):
                return True
        except urllib.error.HTTPError:
            # The server answered (e.g. 302/401/404) — it's up.
            return True
        except (urllib.error.URLError, OSError, TimeoutError):
            # Not listening yet (connection refused) or slow — keep polling.
            time.sleep(interval)
    return False


def _run_login_with_retry(
    config_cmd: str, timeout: float = 120.0, interval: float = 3.0
) -> subprocess.CompletedProcess:
    """Run a `hop3 login` command, retrying on connection failures.

    The login is the definitive readiness test: it must reach the server
    over HTTP. The server may be momentarily unreachable just after first
    boot (it does an initial DB stamp, and the demo bounces services under
    supervisor), so retry while that settles. Non-connection failures (e.g.
    a rejected token) are returned immediately — retrying wouldn't help and
    we don't want to mask a real error for two minutes.

    Returns the final CompletedProcess (success, or the last failure).
    """
    deadline = time.time() + timeout
    while True:
        result = subprocess.run(
            config_cmd,
            shell=True,
            capture_output=True,
            text=True,
            check=False,
            env=cli_env(),
        )
        if result.returncode == 0:
            return result
        # Only retry on explicit connection errors (server still settling
        # after first boot). A non-connection failure — e.g. a rejected
        # token — is returned immediately so we never loop for the full
        # timeout on a permanent error.
        err = result.stderr.lower()
        transient = (
            "could not connect" in err
            or "connection refused" in err
            or "connection reset" in err
            or "timed out" in err
        )
        if not transient or time.time() >= deadline:
            return result
        time.sleep(interval)


def configure_cli(ctx: DemoContext) -> bool:
    """Run Phase 2: Configure the local Hop3 CLI.

    Args:
        ctx: Demo context

    Returns:
        True on success, False on failure.
    """
    from lib.logging import record_timing

    print_header("Configuring CLI", phase=True)
    phase_start = time.time()

    # Start from a clean CLI config: the demo's config home persists across runs,
    # and a stale default context from a prior run (against a different host)
    # would shadow this run's login and send commands to the wrong server with
    # an expired token (401). See reset_cli_home().
    reset_cli_home()

    # Check if hop3 CLI is available
    print_step("Checking hop3 CLI availability...")
    step_start = time.time()
    result = subprocess.run(
        "which hop3", shell=True, capture_output=True, text=True, check=False
    )
    record_timing("which_hop3", time.time() - step_start, category="setup")
    if result.returncode != 0:
        print_error("hop3 CLI not found. Please install it first.")
        print_info("Run: pip install hop3-cli")
        print_phase_result(success=False)
        return False
    print_success("hop3 CLI found")
    pause(ctx.pause_between_steps)

    # Get server URL based on backend
    backend = ctx.get_backend()
    server_url = backend.get_server_url()

    # Wait for the HTTP endpoint to actually accept connections before we try
    # to log in. The server is started under supervisor at the end of the
    # prerequisites phase, but uWSGI needs a few seconds to bind the port —
    # firing `hop3 login` immediately raced that and failed with
    # "Could not connect to <server_url>". Poll until it answers.
    print_step("Waiting for Hop3 server to accept connections...")
    if not _wait_for_http_ready(server_url):
        print_error(f"Hop3 server never became reachable at {server_url}")
        print_info("Check the server: supervisorctl status / journalctl -u hop3-server")
        print_phase_result(success=False)
        return False
    print_success("Server is reachable")

    # Create admin user
    print_step(f"Setting up admin user '{ctx.admin_user}'...")

    if ctx.backend == "docker":
        # For Docker, create admin user directly in the container
        print_info("Creating admin account in Docker container...")
        import re

        from lib.commands import run_ssh

        # Create admin user via hop3-server CLI in container
        # The command outputs an API token that we can use for login
        create_user_cmd = (
            f"echo '{ctx.admin_password}' | "
            f"/home/hop3/venv/bin/hop3-server admin:create "
            f"{ctx.admin_user} {ctx.admin_email} --password-stdin"
        )
        result = run_ssh(ctx, create_user_cmd, check=False, show=False)

        # Extract token from output (admin:create prints a JWT token)
        api_token = None
        if result.returncode == 0:
            # Look for JWT token in output (starts with eyJ)
            token_match = re.search(
                r"(eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)", result.stdout
            )
            if token_match:
                api_token = token_match.group(1)

        if result.returncode != 0 and "already exists" not in result.stderr:
            print_error("Failed to create admin user in container")
            if result.stderr:
                print(f"  {red(result.stderr.strip())}")
            print_phase_result(success=False)
            return False
        print_success(f"Admin user '{ctx.admin_user}' created in container")

        # Configure local CLI to connect to localhost using token-based login
        print_info("Configuring CLI to connect to localhost...")

        if api_token:
            # Use token-based login (more reliable than password)
            login_url = f"{server_url}?token={api_token}"
            config_cmd = f'hop3 login "{login_url}"'
        else:
            # Fallback to password-based login
            config_cmd = (
                f"echo '{ctx.admin_password}' | hop3 login "
                f"--username {ctx.admin_user} "
                f"--url {server_url} "
                f"--password-stdin"
            )

        # Retry the login: the server can still be settling right after
        # first boot (initial DB stamp + a supervisor bounce of the services),
        # so a single attempt may hit a brief window where the port is not
        # accepting yet — even though the readiness poll above just saw it up.
        result = _run_login_with_retry(config_cmd)
        if result.returncode != 0:
            print_error("Failed to configure CLI for Docker")
            if result.stderr:
                print(f"  {red(result.stderr.strip())}")
            print_phase_result(success=False)
            return False
    else:
        # For SSH, use the standard init command
        print_info("This will connect via SSH and create/login the admin account.")

        init_cmd = (
            f"echo '{ctx.admin_password}' | hop3 init "
            f"--ssh {ctx.ssh_target} "
            f"--username {ctx.admin_user} "
            f"--email {ctx.admin_email} "
            f"--url {server_url} "
            f"--password-stdin --yes"
        )
        if ctx.output_level >= OutputLevel.NORMAL:
            print_command(
                f"hop3 init --ssh {ctx.ssh_target} --username {ctx.admin_user} --email {ctx.admin_email}"
            )

        step_start = time.time()
        result = subprocess.run(
            init_cmd,
            shell=True,
            capture_output=True,
            text=True,
            check=False,
            env=cli_env(),
        )
        record_timing("hop3_init", time.time() - step_start, category="setup")
        if result.stdout and ctx.output_level >= OutputLevel.VERBOSE:
            print(result.stdout)

        if result.returncode != 0:
            if "already exists" in result.stderr:
                print_info("Admin user already exists, attempting login...")
                login_cmd = (
                    f"hop3 login --ssh {ctx.ssh_target} "
                    f"--username {ctx.admin_user} "
                    f"--url {server_url}"
                )
                step_start = time.time()
                result = subprocess.run(
                    login_cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    check=False,
                    env=cli_env(),
                )
                record_timing("hop3_login", time.time() - step_start, category="setup")
                if result.stdout and ctx.output_level >= OutputLevel.VERBOSE:
                    print(result.stdout)
                if result.returncode != 0:
                    print_error("Failed to login")
                    if result.stderr:
                        print(f"  {red(result.stderr.strip())}")
                    print_phase_result(success=False)
                    return False
                print_success(f"Logged in as '{ctx.admin_user}'")
            else:
                print_error("Failed to create admin user")
                if result.stderr:
                    print(f"  {red(result.stderr.strip())}")
                print_phase_result(success=False)
                return False
        else:
            print_success(f"Admin user '{ctx.admin_user}' created")
    pause(ctx.pause_between_steps)

    # Verify authentication (quiet in non-verbose mode)
    print_step("Verifying authentication...")
    step_start = time.time()
    try:
        run_hop3("auth whoami", quiet=(ctx.output_level < OutputLevel.VERBOSE))
    except Exception:
        print_phase_result(success=False)
        return False
    record_timing("auth_whoami", time.time() - step_start, category="setup")
    print_success("Authentication verified")
    record_timing("configure_cli_phase", time.time() - phase_start, category="phase")
    print_phase_result(success=True)

    return True


def _extract_demo_title(demo_dir: Path) -> str | None:
    """Extract TITLE from demo-script.py without fully loading the module.

    Args:
        demo_dir: Path to demo directory

    Returns:
        Title string if found, None otherwise
    """
    import re

    script_path = demo_dir / "demo-script.py"
    if not script_path.exists():
        return None

    try:
        content = script_path.read_text()
        # Match TITLE = "..." or TITLE = '...'
        match = re.search(r'^TITLE\s*=\s*["\'](.+?)["\']', content, re.MULTILINE)
        if match:
            title = match.group(1)
            # Remove "Demo N: " prefix to get just the description
            title = re.sub(r'^Demo\s+\d+:\s*', '', title)
            return title
    except Exception:
        pass
    return None


def run_demo(
    ctx: DemoContext,
    demo_name: str,
    demo_dir: Path,
    *,
    is_generic: bool,
) -> DemoResult:
    """Run a single demo.

    Args:
        ctx: Demo context
        demo_name: Display name for the demo
        demo_dir: Path to the demo directory
        is_generic: If True, run generic demo instead of demo-script.py

    Returns:
        DemoResult with status, timing, and error info.
    """
    start_time = time.time()
    title = demo_name
    error_msg = None
    app_name = demo_name  # Default app name for failure capture

    # Extract short description for quiet mode output
    short_desc = _extract_demo_title(demo_dir)

    # Start logging for this demo
    start_demo_logging(demo_name)
    log_section(
        "main",
        f"Starting demo: {demo_name}",
        f"Demo directory: {demo_dir}\nGeneric: {is_generic}",
    )

    # Reclaim server disk before each demo so a long run (50+ deploys) doesn't
    # exhaust the disk — the cascading-failure + 600s-timeout cause.
    from lib.server import prune_server_disk

    prune_server_disk(ctx)

    # Show demo start - in quiet mode show "demo01 (description)...", in normal mode full header
    if ctx.output_level == OutputLevel.QUIET:
        if short_desc:
            print(f"{demo_name} ({short_desc})... ", end="", flush=True)
        else:
            print(f"{demo_name}... ", end="", flush=True)

    try:
        if is_generic:
            from lib.generic_demo import run_generic_demo

            if ctx.output_level >= OutputLevel.NORMAL:
                print_header(f"Running: {demo_name}")
            run_generic_demo(ctx, demo_dir)
            duration = time.time() - start_time
            if ctx.output_level >= OutputLevel.NORMAL:
                print_success(f"Demo '{demo_name}' completed successfully")
            print_phase_result(success=True)
            log_section(
                "main", "Demo completed", f"Status: PASS\nDuration: {duration:.2f}s"
            )
            end_demo_logging()
            return DemoResult(
                name=demo_name,
                title=title,
                status="pass",
                duration=duration,
            )
        # Load and run custom demo script
        script_path = demo_dir / "demo-script.py"
        module = load_demo_module(script_path)
        if not module:
            duration = time.time() - start_time
            print_phase_result(success=False)
            log_section("main", "Demo failed", "Error: Failed to load demo script")
            end_demo_logging()
            return DemoResult(
                name=demo_name,
                title=title,
                status="fail",
                duration=duration,
                error="Failed to load demo script",
            )

        # Get demo info
        title = getattr(module, "TITLE", demo_name)
        description = getattr(module, "DESCRIPTION", "")
        app_name = getattr(module, "APP_NAME", demo_name)
        requires = getattr(module, "REQUIRES", None)

        # Check if demo requirements are satisfied by the current backend
        satisfied, reason = ctx.check_requirements(requires)
        if not satisfied:
            duration = time.time() - start_time
            skip_msg = f"Skipped: {reason}"
            if ctx.output_level >= OutputLevel.NORMAL:
                print_info(f"Skipping {demo_name}: {reason}")
            elif ctx.output_level == OutputLevel.QUIET:
                # Complete the dangling "demoNN (desc)... " progress line.
                print(f"{yellow('SKIP')} ({reason})")
            log_section("main", "Demo skipped", skip_msg)
            end_demo_logging()
            return DemoResult(
                name=demo_name,
                title=title,
                status="skip",
                duration=duration,
                error=skip_msg,
            )

        if ctx.output_level >= OutputLevel.NORMAL:
            print_header(f"Running: {title}")
            if description:
                print(dim(description))
                print()

        # Run demo's main function
        if hasattr(module, "run"):
            module.run(ctx)
            duration = time.time() - start_time
            if ctx.output_level >= OutputLevel.NORMAL:
                print_success(f"Demo '{demo_name}' completed successfully")
            print_phase_result(success=True)
            log_section(
                "main", "Demo completed", f"Status: PASS\nDuration: {duration:.2f}s"
            )
            end_demo_logging()
            return DemoResult(
                name=demo_name,
                title=title,
                status="pass",
                duration=duration,
            )
        duration = time.time() - start_time
        print_phase_result(success=False)
        log_section("main", "Demo failed", "Error: Demo has no run() function")
        end_demo_logging()
        return DemoResult(
            name=demo_name,
            title=title,
            status="fail",
            duration=duration,
            error="Demo has no run() function",
        )

    except KeyboardInterrupt:
        print()
        print_error("Demo interrupted by user")
        duration = time.time() - start_time
        log_section("main", "Demo interrupted", "Interrupted by user")
        end_demo_logging()
        return DemoResult(
            name=demo_name,
            title=title,
            status="fail",
            duration=duration,
            error="Interrupted by user",
        )
    except Exception as e:
        error_msg = str(e)
        print_error(f"Demo '{demo_name}' failed: {e}")
        print_phase_result(success=False)

        # Capture failure debug info (container logs, app info, etc.)
        log_section("main", "Demo failed", f"Error: {error_msg}")
        try:
            capture_failure_debug(ctx, app_name)
        except Exception as capture_err:
            log_section("main", "Failed to capture debug info", str(capture_err))

        # Actionable reason under the FAIL line (quiet) / log hint (normal).
        log_session = get_log_session()
        log_dir = (
            log_session.current_demo_dir
            if log_session and log_session.current_demo_dir
            else None
        )
        print_failure_detail(error_msg, log_dir)
        if log_dir:
            print_info(f"  Logs: {log_dir}")

        # Log full traceback to file (not console)
        import traceback

        tb_str = traceback.format_exc()
        log_section("traceback", "Exception traceback", tb_str)

        duration = time.time() - start_time
        end_demo_logging()
        return DemoResult(
            name=demo_name,
            title=title,
            status="fail",
            duration=duration,
            error=error_msg,
        )
