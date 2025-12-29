# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 31: Native Python + PostgreSQL Addon.

Demonstrates deploying a native Python application with PostgreSQL addon.
This is the native equivalent of demo15 (Docker + PostgreSQL).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 31: Native Python + PostgreSQL"
DESCRIPTION = """
Demonstrates native Python deployment with PostgreSQL addon:
  - Building and deploying a native Python application
  - Creating a PostgreSQL database via addon
  - Connecting the app to PostgreSQL
  - Testing database operations
"""

APP_NAME = "demo31"
APP_DIR = Path(__file__).parent / "app"
DB_NAME = "demo31-db"


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

    app_hostname = ctx.get_app_hostname(APP_NAME)
    app_url = f"https://{app_hostname}"

    # Show app structure
    print_header("Deploying Native Python + PostgreSQL Application")

    show_app_structure(
        APP_NAME,
        [
            ("app.py", "Flask application with PostgreSQL support"),
            ("requirements.txt", "Python dependencies (flask, psycopg2)"),
            ("hop3.toml", "Hop3 configuration (native Python builder)"),
        ],
    )
    print_info("This demo shows a native Python app connecting to a PostgreSQL addon.")
    print_info("Unlike demo15, this does NOT use Docker.")
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
    test_app_via_curl(ctx, app_url, expected_content="Welcome to demo31")
    pause(ctx.pause_between_steps)

    # Test database status - should show not_configured
    print_header("Step 3: Check Database Status (Before Addon)")
    print_step("Testing /db-status endpoint...")
    test_app_via_curl(ctx, f"{app_url}/db-status", expected_content="not_configured")
    pause(ctx.pause_between_steps)

    # Create PostgreSQL addon
    print_header("Step 4: Create PostgreSQL Database")
    print_step(f"Creating PostgreSQL database '{DB_NAME}'...")
    result = run_hop3(f"addons:create postgres {DB_NAME}", check=False)

    postgres_available = result.returncode == 0
    if not postgres_available:
        print_warning("PostgreSQL creation failed.")
        if result.stderr:
            print_info(f"  Error: {result.stderr.strip()}")
    else:
        print_success(f"PostgreSQL database '{DB_NAME}' created.")
    pause(ctx.pause_between_steps)

    # Attach database to app
    if postgres_available:
        print_header("Step 5: Attach Database to Application")
        print_step(f"Attaching '{DB_NAME}' to '{APP_NAME}'...")
        result = run_hop3(
            f"addons:attach {DB_NAME} --app {APP_NAME} --service-type postgres",
            check=False,
        )

        if result.returncode != 0:
            print_warning("Failed to attach database.")
            postgres_available = False
        else:
            print_success("Database attached. DATABASE_URL is now set.")
        pause(ctx.pause_between_steps)

    # Redeploy to pick up DATABASE_URL
    if postgres_available:
        print_header("Step 6: Redeploy to Apply Configuration")
        print_step("Redeploying application with DATABASE_URL...")
        redeploy_app(ctx, APP_NAME, APP_DIR)
        wait_for_app(seconds=5)

        # Test database connection
        print_header("Step 7: Verify Database Connection")
        print_step("Testing /db-status endpoint...")
        test_app_via_curl(ctx, f"{app_url}/db-status", expected_content="connected")
        print_success("Native Python app connected to PostgreSQL!")
        pause(ctx.pause_between_steps)

        # Test database operations
        print_header("Step 8: Test Database Operations")
        print_step("Testing /db-test endpoint (create table, insert, query)...")
        test_app_via_curl(ctx, f"{app_url}/db-test", expected_content="success")
        print_success("Database operations working!")
        pause(ctx.pause_between_steps)

        # Cleanup database
        print_header("Step 9: Cleanup Database")
        print_step("Detaching and destroying database...")
        run_hop3(
            f"addons:detach {DB_NAME} --app {APP_NAME} --service-type postgres",
            check=False,
        )
        run_hop3(f"addons:destroy {DB_NAME} --service-type postgres", check=False)
        print_success("Database cleaned up.")
        pause(ctx.pause_between_steps)
    else:
        print_header("PostgreSQL Addon Commands")
        print_info("When PostgreSQL is available:")
        print_info(f"  hop3 addons:create postgres {DB_NAME}")
        print_info(f"  hop3 addons:attach {DB_NAME} --app {APP_NAME} --service-type postgres")
        print_blank()
        pause(ctx.pause_between_steps)

    # Cleanup app
    cleanup_app(ctx, APP_NAME, app_url)

    if postgres_available:
        print_success("Demo 31 completed: Native Python + PostgreSQL workflow demonstrated.")
    else:
        print_success("Demo 31 completed: Native Python app deployed (PostgreSQL unavailable).")
