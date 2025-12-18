# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 38: BookStack.

Demonstrates deploying BookStack, a self-hosted documentation wiki,
with Docker and MySQL addon.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 38: BookStack"
DESCRIPTION = """
Demonstrates deploying BookStack with Hop3:
  - Docker-based deployment
  - MySQL addon for data storage
  - Self-hosted documentation wiki
  - Simple knowledge management
"""

APP_NAME = "demo38"
APP_DIR = Path(__file__).parent / "app"
MYSQL_NAME = "demo38-db"


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
    print_header("Deploying BookStack")

    show_app_structure(
        APP_NAME,
        [
            ("Dockerfile", "Docker image with PHP, Apache, and BookStack"),
            ("start.sh", "Startup script with MySQL configuration"),
            ("hop3.toml", "Hop3 configuration with [[provider]] section"),
        ],
    )
    print_info("BookStack is a simple, self-hosted documentation platform.")
    print_info("Perfect for team wikis, knowledge bases, and documentation.")
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
    print_info("Building Docker image (this may take a few minutes)...")
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
    wait_for_app(seconds=45, message="Waiting for BookStack to start (running migrations)...")
    check_app_status(ctx, APP_NAME)

    # Test main endpoint
    print_header("Step 5: Test Application")
    test_app_via_curl(ctx, app_url, expected_content="BookStack")
    print_success("BookStack is running!")
    print_blank()
    print_info("Default login: admin@admin.com / password")
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
    print_success("Demo 38 completed: BookStack deployed successfully.")
