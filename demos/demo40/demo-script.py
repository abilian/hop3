# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 40: Ghost Blogging Platform.

Demonstrates deploying Ghost, a modern publishing platform,
with Docker and MySQL addon.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 40: Ghost Blogging Platform"
DESCRIPTION = """
Demonstrates deploying Ghost with Hop3:
  - Docker-based deployment (Node.js)
  - MySQL addon for data storage
  - Modern publishing platform
  - Clean, minimal blogging
"""

APP_NAME = "demo40"
APP_DIR = Path(__file__).parent / "app"
MYSQL_NAME = "demo40-db"


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
        print_warning,
        redeploy_app,
        set_hostname,
        show_app_structure,
        show_file_content,
        test_app_via_curl,
        wait_for_app,
    )
    from lib.commands import run_hop3
    from lib.server import ensure_docker, ensure_mysql

    app_hostname = ctx.hostname
    app_url = f"https://{app_hostname}"

    # Ensure Docker and MySQL are available
    ensure_docker(ctx)
    ensure_mysql(ctx)
    pause(ctx.pause_between_steps)

    # Clean up any leftover MySQL addon from previous failed runs
    run_hop3(f"addons:destroy {MYSQL_NAME} --service-type mysql", check=False, show=False)

    # Show app structure
    print_header("Deploying Ghost Blogging Platform")

    show_app_structure(
        APP_NAME,
        [
            ("Dockerfile", "Docker image based on ghost:5-alpine"),
            ("start.sh", "Startup script with MySQL configuration"),
            ("hop3.toml", "Hop3 configuration with [[provider]] section"),
        ],
    )
    print_info("Ghost is a powerful publishing platform for professional bloggers.")
    print_info("This demo uses MySQL via the [[provider]] declaration in hop3.toml.")
    print_blank()
    pause(ctx.pause_between_steps)

    # Show hop3.toml
    show_file_content(APP_DIR / "hop3.toml", "hop3.toml:")
    pause(ctx.pause_between_steps)

    # Create MySQL addon
    print_header("Step 1: Create MySQL Database")
    print_step(f"Creating MySQL instance '{MYSQL_NAME}'...")
    result = run_hop3(f"addons:create mysql {MYSQL_NAME}", check=False)

    if result.returncode != 0:
        print_warning("MySQL creation failed.")
        if result.stderr:
            print_info(f"  Error: {result.stderr.strip()}")
        cleanup_app(ctx, APP_NAME, app_url)
        return

    print_success(f"MySQL instance '{MYSQL_NAME}' created.")
    pause(ctx.pause_between_steps)

    # Deploy the application
    print_header("Step 2: Deploy Application")
    print_info("Building Docker image...")
    deploy_app(ctx, APP_NAME, APP_DIR)
    set_hostname(ctx, APP_NAME, app_hostname)

    # Attach MySQL addon
    print_header("Step 3: Attach MySQL")
    print_step(f"Attaching '{MYSQL_NAME}' to '{APP_NAME}'...")
    result = run_hop3(
        f"addons:attach {MYSQL_NAME} --app {APP_NAME} --service-type mysql",
        check=False,
    )
    if result.returncode != 0:
        print_warning("Failed to attach MySQL.")
    else:
        print_success("MySQL attached. DATABASE_URL is now set.")
    pause(ctx.pause_between_steps)

    # Redeploy with database
    print_header("Step 4: Redeploy with Database")
    redeploy_app(ctx, APP_NAME, APP_DIR)
    wait_for_app(seconds=20, message="Waiting for Ghost to start...")
    check_app_status(ctx, APP_NAME)

    # Test main endpoint
    print_header("Step 5: Test Application")
    # Ghost homepage contains "Ghost" in the page
    test_app_via_curl(ctx, app_url, expected_content="Ghost")
    print_success("Ghost is running!")
    print_blank()
    print_info("Visit /ghost to access the admin panel and create your account.")
    pause(ctx.pause_between_steps)

    # Cleanup
    print_header("Step 6: Cleanup")
    print_step("Detaching and destroying MySQL...")
    run_hop3(
        f"addons:detach {MYSQL_NAME} --app {APP_NAME} --service-type mysql",
        check=False,
    )
    run_hop3(f"addons:destroy {MYSQL_NAME} --service-type mysql", check=False)
    print_success("MySQL cleaned up.")

    cleanup_app(ctx, APP_NAME, app_url)
    print_success("Demo 40 completed: Ghost deployed successfully.")
