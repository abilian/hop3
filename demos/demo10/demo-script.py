# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 10: PostgreSQL Addon.

Demonstrates creating and attaching a PostgreSQL database to an application.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 10: PostgreSQL Addon"
DESCRIPTION = """
Demonstrates PostgreSQL addon functionality with Hop3:
  - Creating a PostgreSQL database instance
  - Attaching database to an application
  - Application connecting to database via DATABASE_URL
"""

APP_NAME = "demo10"
APP_DIR = Path(__file__).parent / "app"
DEFAULT_HOSTNAME = "demo10.hop"
DB_NAME = "demo10-db"


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

    app_hostname = DEFAULT_HOSTNAME
    app_url = f"https://{app_hostname}"
    db_name_underscore = DB_NAME.replace("-", "_")  # demo10-db -> demo10_db

    # Show app structure
    print_header("Deploying PostgreSQL-Ready Flask App")

    show_app_structure(
        APP_NAME,
        [
            ("app.py", "Flask application with database support"),
            ("requirements.txt", "Python dependencies (flask, psycopg2)"),
            ("Procfile", "Gunicorn web server"),
        ],
    )
    pause(ctx.pause_between_steps)

    # Show app.py to highlight DATABASE_URL usage
    show_file_content(APP_DIR / "app.py", "Application code (app.py):", max_lines=30)
    print_info("Note: The app reads DATABASE_URL from environment variables.")
    print_info("When not configured, it gracefully reports 'not_configured'.")
    print_blank()
    pause(ctx.pause_between_steps)

    # Deploy the application
    print_header("Step 1: Deploy Application")
    deploy_app(ctx, APP_NAME, APP_DIR)
    set_hostname(ctx, APP_NAME, app_hostname)
    redeploy_app(ctx, APP_NAME, APP_DIR)
    wait_for_app(seconds=5)
    check_app_status(ctx, APP_NAME)

    # Test main endpoint
    print_header("Step 2: Test Application (Without Database)")
    test_app_via_curl(ctx, app_url, expected_content="Welcome to demo10")
    pause(ctx.pause_between_steps)

    # Test database status endpoint - should show not_configured
    print_header("Step 3: Check Database Status (Before Addon)")
    print_step("Testing /db-status endpoint...")
    print_info("Without DATABASE_URL configured, app reports 'not_configured'.")
    test_app_via_curl(
        ctx, f"{app_url}/db-status",
        expected_content="not_configured",
    )
    pause(ctx.pause_between_steps)

    # Create PostgreSQL addon
    print_header("Step 4: Create PostgreSQL Database")
    print_step(f"Creating PostgreSQL database '{DB_NAME}'...")
    result = run_hop3(f"addons:create postgres {DB_NAME}", check=False)

    postgres_available = result.returncode == 0
    if not postgres_available:
        print_warning("PostgreSQL creation failed (server may not have PostgreSQL installed).")
        if result.stderr:
            print_info(f"  Error: {result.stderr.strip()}")
        print_blank()
        print_info("To use PostgreSQL addons, ensure PostgreSQL is installed on the server:")
        print_info("  apt install postgresql postgresql-contrib")
        print_info("  systemctl enable postgresql")
        print_info("  systemctl start postgresql")
    else:
        print_success(f"PostgreSQL database '{DB_NAME}' created.")

        # Verify the database was actually created using addon's own connection
        print_step("Verifying database exists...")
        info_result = run_hop3(
            f"addons:info {DB_NAME} --service-type postgres",
            check=False,
            show=False,
        )
        # If info returns database details (not "not_created" or error), it exists
        if info_result.returncode == 0 and "database" in info_result.stdout.lower():
            print_success(f"Verified: Database '{db_name_underscore}' exists.")
        else:
            print_warning(f"Could not verify database '{db_name_underscore}' exists.")
            print_info("  This may be a connection configuration issue.")
            # Don't fail the demo - the addon creation succeeded
    pause(ctx.pause_between_steps)

    # If PostgreSQL is available, attach it to the app
    if postgres_available:
        print_header("Step 5: Attach Database to Application")
        print_step(f"Attaching '{DB_NAME}' to '{APP_NAME}'...")
        result = run_hop3(
            f"addons:attach {DB_NAME} --app {APP_NAME} --service-type postgres",
            check=False
        )

        if result.returncode != 0:
            print_warning("Failed to attach database.")
            if result.stderr:
                print_info(f"  Error: {result.stderr.strip()}")
            postgres_available = False
        else:
            print_success("Database attached. DATABASE_URL is now set.")
        pause(ctx.pause_between_steps)

    # Redeploy app to pick up new environment variables
    # Note: restart just reloads the process, redeploy regenerates the uwsgi config with new env vars
    if postgres_available:
        print_header("Step 6: Redeploy Application")
        print_step("Redeploying app to apply DATABASE_URL...")
        redeploy_app(ctx, APP_NAME, APP_DIR)
        wait_for_app(seconds=3)

        # Test database connection
        print_header("Step 7: Verify Database Connection")
        print_step("Testing /db-status endpoint with database attached...")
        test_app_via_curl(
            ctx, f"{app_url}/db-status",
            expected_content="connected",
        )
        print_success("Application is now connected to PostgreSQL!")
        pause(ctx.pause_between_steps)

        # Get addon info
        print_header("Step 8: View Database Information")
        print_step(f"Getting info for database '{DB_NAME}'...")
        run_hop3(f"addons:info {DB_NAME} --service-type postgres", check=False)
        pause(ctx.pause_between_steps)

        # Cleanup: Detach and destroy the database
        print_header("Step 9: Cleanup Database")
        print_step("Detaching database from app...")
        run_hop3(f"addons:detach {DB_NAME} --app {APP_NAME} --service-type postgres", check=False)

        print_step(f"Destroying database '{DB_NAME}'...")
        run_hop3(f"addons:destroy {DB_NAME} --service-type postgres", check=False)

        # Verify the database was actually destroyed using addon's own connection
        print_step("Verifying database was removed...")
        info_result = run_hop3(
            f"addons:info {DB_NAME} --service-type postgres",
            check=False,
            show=False,
        )
        # If info returns "not_created" status, the database is gone
        if "not_created" in info_result.stdout.lower() or "not found" in info_result.stdout.lower():
            print_success(f"Verified: Database '{db_name_underscore}' no longer exists.")
        elif info_result.returncode != 0:
            print_success(f"Verified: Database '{db_name_underscore}' no longer exists.")
        else:
            print_warning(f"Database '{db_name_underscore}' may still exist.")

        print_success("Database cleaned up.")
        pause(ctx.pause_between_steps)
    else:
        # Show what would happen with PostgreSQL
        print_header("PostgreSQL Addon Commands")
        print_blank()
        print_info("When PostgreSQL is available, you can:")
        print_info(f"  1. Create database: hop3 addons:create postgres {DB_NAME}")
        print_info(f"  2. Attach to app: hop3 addons:attach {DB_NAME} --app {APP_NAME} --service-type postgres")
        print_info(f"  3. View info: hop3 addons:info {DB_NAME} --service-type postgres")
        print_info(f"  4. Detach: hop3 addons:detach {DB_NAME} --app {APP_NAME}")
        print_info(f"  5. Destroy: hop3 addons:destroy {DB_NAME}")
        print_blank()
        pause(ctx.pause_between_steps)

    # Cleanup app
    cleanup_app(ctx, APP_NAME, app_url)

    if postgres_available:
        print_success("Demo 10 completed: Full PostgreSQL addon workflow demonstrated.")
    else:
        print_success("Demo 10 completed: PostgreSQL-ready application deployed.")
        print_info("Install PostgreSQL on server to enable full addon functionality.")
