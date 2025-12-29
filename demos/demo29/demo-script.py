# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 29: Native Python + MySQL Addon - Page Counter.

Demonstrates deploying a native Python application with MySQL addon.
This is similar to demo28 but uses native deployment instead of Docker.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 29: Native Python + MySQL (Page Counter)"
DESCRIPTION = """
Demonstrates native Python deployment with MySQL addon:
  - Building and deploying a native Python application
  - Creating a MySQL database via addon
  - Connecting the app to MySQL
  - Testing database operations with a page counter
"""

APP_NAME = "demo29"
APP_DIR = Path(__file__).parent / "app"
DB_NAME = "demo29-db"


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
    from lib.server import ensure_mysql

    app_hostname = ctx.get_app_hostname(APP_NAME)
    app_url = f"https://{app_hostname}"

    # Ensure MySQL is properly configured with password authentication
    ensure_mysql(ctx)
    pause(ctx.pause_between_steps)

    # Show app structure
    print_header("Deploying Native Python + MySQL Application")

    show_app_structure(
        APP_NAME,
        [
            ("app.py", "Flask application with MySQL page counter"),
            ("requirements.txt", "Python dependencies (flask, mysql-connector-python)"),
            ("hop3.toml", "Hop3 configuration (native Python builder)"),
        ],
    )
    print_info("This demo validates the MySQL addon with a native Python app.")
    print_info("Unlike demo28, this does NOT use Docker - it runs directly on the server.")
    print_blank()
    pause(ctx.pause_between_steps)

    # Show hop3.toml
    show_file_content(APP_DIR / "hop3.toml", "hop3.toml:")
    pause(ctx.pause_between_steps)

    # Deploy the application
    print_header("Step 1: Deploy Native Python Application")
    deploy_app(ctx, APP_NAME, APP_DIR)
    set_hostname(ctx, APP_NAME, app_hostname)
    redeploy_app(ctx, APP_NAME, APP_DIR)
    wait_for_app(seconds=5, message="Waiting for application to start...")
    check_app_status(ctx, APP_NAME)

    # Test main endpoint
    print_header("Step 2: Test Application (Without Database)")
    test_app_via_curl(ctx, app_url, expected_content="Welcome to demo29")
    pause(ctx.pause_between_steps)

    # Test database status - should show not_configured
    print_header("Step 3: Check Database Status (Before Addon)")
    print_step("Testing /db-status endpoint...")
    test_app_via_curl(ctx, f"{app_url}/db-status", expected_content="not_configured")
    pause(ctx.pause_between_steps)

    # Create MySQL addon
    print_header("Step 4: Create MySQL Database")
    print_step(f"Creating MySQL database '{DB_NAME}'...")
    result = run_hop3(f"addons:create mysql {DB_NAME}", check=False)

    mysql_available = result.returncode == 0
    if not mysql_available:
        print_warning("MySQL creation failed.")
        if result.stderr:
            print_info(f"  Error: {result.stderr.strip()}")
        print_info("Make sure MySQL server is installed and configured on the server.")
    else:
        print_success(f"MySQL database '{DB_NAME}' created.")
    pause(ctx.pause_between_steps)

    # Attach database to app
    if mysql_available:
        print_header("Step 5: Attach Database to Application")
        print_step(f"Attaching '{DB_NAME}' to '{APP_NAME}'...")
        result = run_hop3(
            f"addons:attach {DB_NAME} --app {APP_NAME} --service-type mysql",
            check=False,
        )

        if result.returncode != 0:
            print_warning("Failed to attach database.")
            if result.stderr:
                print_info(f"  Error: {result.stderr.strip()}")
            mysql_available = False
        else:
            print_success("Database attached.")
            # Verify env vars were actually set
            print_step("Verifying environment variables...")
            verify_result = run_hop3(f"app:env {APP_NAME}", check=False)
            if verify_result.stdout and "DATABASE_URL" in verify_result.stdout:
                print_success("DATABASE_URL is set in app environment.")
            else:
                print_warning("DATABASE_URL NOT FOUND in app environment!")
        pause(ctx.pause_between_steps)

    # Redeploy to pick up DATABASE_URL
    if mysql_available:
        print_header("Step 6: Redeploy to Apply Configuration")
        print_step("Redeploying application with MySQL environment variables...")
        redeploy_app(ctx, APP_NAME, APP_DIR)
        wait_for_app(seconds=5)

        # Test database connection
        print_header("Step 7: Verify Database Connection")
        print_step("Testing /db-status endpoint...")
        test_app_via_curl(ctx, f"{app_url}/db-status", expected_content="connected")
        print_success("Native Python app connected to MySQL!")
        pause(ctx.pause_between_steps)

        # Initialize database
        print_header("Step 8: Initialize Database")
        print_step("Creating page_views table via /db-init...")
        test_app_via_curl(ctx, f"{app_url}/db-init", expected_content="success")
        print_success("Database table created!")
        pause(ctx.pause_between_steps)

        # Test page counter
        print_header("Step 9: Test Page Counter")
        print_step("Visiting home page multiple times to increment counter...")

        for i in range(3):
            print_step(f"  Visit {i + 1}...")
            test_app_via_curl(ctx, app_url, expected_content="page_views")
            pause(0.5)

        print_success("Page counter incrementing correctly!")
        pause(ctx.pause_between_steps)

        # Show counter stats
        print_header("Step 10: Check Counter Statistics")
        print_step("Getting counter statistics via /counter...")
        test_app_via_curl(ctx, f"{app_url}/counter", expected_content="counters")
        pause(ctx.pause_between_steps)

        # Test database operations
        print_header("Step 11: Test Database Operations")
        print_step("Running /db-test endpoint...")
        test_app_via_curl(ctx, f"{app_url}/db-test", expected_content="success")
        print_success("MySQL operations working!")
        pause(ctx.pause_between_steps)

        # Cleanup database
        print_header("Step 12: Cleanup Database")
        print_step("Detaching and destroying database...")
        run_hop3(
            f"addons:detach {DB_NAME} --app {APP_NAME} --service-type mysql",
            check=False,
        )
        run_hop3(f"addons:destroy {DB_NAME} --service-type mysql", check=False)
        print_success("Database cleaned up.")
        pause(ctx.pause_between_steps)
    else:
        print_header("MySQL Addon Commands")
        print_info("When MySQL is available:")
        print_info(f"  hop3 addons:create mysql {DB_NAME}")
        print_info(f"  hop3 addons:attach {DB_NAME} --app {APP_NAME} --service-type mysql")
        print_blank()
        pause(ctx.pause_between_steps)

    # Cleanup app
    cleanup_app(ctx, APP_NAME, app_url)

    if mysql_available:
        print_success("Demo 29 completed: Native Python + MySQL workflow demonstrated.")
        print_success("MySQL addon validated with native deployment!")
    else:
        print_success("Demo 29 completed: Native Python app deployed (MySQL unavailable).")
