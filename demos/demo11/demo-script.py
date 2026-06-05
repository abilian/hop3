# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 11: Background Workers.

Demonstrates deploying an application with multiple process types.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 11: Background Workers"
DESCRIPTION = """
Demonstrates background worker processes with Hop3:
  - Procfile with multiple process types (web + worker)
  - Process scaling with ps scale
  - Viewing process status with ps
"""

APP_NAME = "demo11"
APP_DIR = Path(__file__).parent / "app"


def run(ctx: DemoContext) -> None:
    """Run the demo."""
    from lib import (
        check_app_status,
        cleanup_app,
        deploy_app,
        pause,
        print_blank,
        print_header,
        print_info,
        print_step,
        print_success,
        redeploy_app,
        set_hostname,
        show_app_structure,
        show_file_content,
        test_app_via_curl,
        wait_for_app,
        wait_for_app_ready,
    )
    from lib.commands import run_hop3

    app_hostname = ctx.get_app_hostname(APP_NAME)
    app_url = f"https://{app_hostname}"

    # Show app structure
    print_header("Deploying App with Background Worker")

    show_app_structure(
        APP_NAME,
        [
            ("app.py", "Flask web application"),
            ("worker.py", "Background worker process"),
            ("requirements.txt", "Python dependencies"),
            ("Procfile", "Defines web + worker processes"),
        ],
    )
    pause(ctx.pause_between_steps)

    # Show Procfile to highlight multiple process types
    show_file_content(APP_DIR / "Procfile", "Procfile (multiple process types):")
    print_info("The Procfile defines two process types:")
    print_info("  - web: Handles HTTP requests")
    print_info("  - worker: Processes background tasks")
    print_blank()
    pause(ctx.pause_between_steps)

    # Show worker code
    show_file_content(APP_DIR / "worker.py", "Worker code (worker.py):", max_lines=25)
    pause(ctx.pause_between_steps)

    # Deploy the application
    print_header("Step 1: Deploy Application")
    deploy_app(ctx, APP_NAME, APP_DIR)

    # Set hostname
    set_hostname(ctx, APP_NAME, app_hostname)
    redeploy_app(ctx, APP_NAME, APP_DIR)
    # Wait for app to be ready (tests direct connection)
    wait_for_app_ready(APP_NAME, timeout=30.0)
    # Give nginx extra time to reload after config change
    wait_for_app(seconds=2, message="Waiting for nginx to reload...")

    # Check app status
    check_app_status(ctx, APP_NAME)

    # Show process status
    print_header("Step 2: View Process Status")
    print_step("Running 'hop3 ps' to see process types...")
    run_hop3(f"ps {APP_NAME}")
    pause(ctx.pause_between_steps)

    # Test the web endpoint
    print_header("Step 3: Test Web Process")
    test_app_via_curl(ctx, app_url, expected_content="Welcome to demo11")
    pause(ctx.pause_between_steps)

    # Enqueue a task
    print_header("Step 4: Enqueue Background Task")
    print_step("Sending a task to the queue via /enqueue/hello...")
    test_app_via_curl(
        ctx, f"{app_url}/enqueue/hello-from-demo",
        expected_content="queued",
    )
    pause(ctx.pause_between_steps)

    # Check tasks
    print_step("Checking task status via /tasks...")
    wait_for_app(seconds=3, message="Waiting for worker to process task...")
    test_app_via_curl(
        ctx, f"{app_url}/tasks",
        expected_content="tasks",
    )
    pause(ctx.pause_between_steps)

    # Demonstrate scaling
    print_header("Step 5: Process Scaling")
    print_step("Scaling worker to 2 instances...")
    result = run_hop3(f"ps scale {APP_NAME} worker=2", check=False)
    if result.returncode == 0:
        print_success("Worker scaled to 2 instances.")
    else:
        print_info("Scaling may not be fully implemented yet.")
    pause(ctx.pause_between_steps)

    # Show updated process status
    print_step("Checking updated process status...")
    run_hop3(f"ps {APP_NAME}")
    pause(ctx.pause_between_steps)

    # Scale back down
    print_step("Scaling worker back to 1 instance...")
    run_hop3(f"ps scale {APP_NAME} worker=1", check=False)

    # Cleanup
    cleanup_app(ctx, APP_NAME, app_url)

    print_success("Demo 11 completed: Background workers demonstrated.")
