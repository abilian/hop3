# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 33: Declarative PostgreSQL Provider.

Demonstrates the [[provider]] section in hop3.toml for declaring addon dependencies.
This demo shows how to use the declarative format to specify that an app requires
a PostgreSQL database.

Note: Currently, addons are still created manually via CLI commands.
The [[provider]] section documents the app's requirements and will be used
for automatic provisioning in a future version.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 33: Declarative PostgreSQL Provider"
DESCRIPTION = """
Demonstrates the [[provider]] section in hop3.toml:
  - Declaring addon requirements with [[provider]]
  - App uses 'name = "postgres"' in provider section
  - Shows how declarative provisioning will work
  - Currently creates addons manually (auto-provisioning coming)
"""

APP_NAME = "demo33"
APP_DIR = Path(__file__).parent / "app"
DEFAULT_HOSTNAME = "demo33.hop"
DB_NAME = "demo33-db"


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

    # Clean up any leftover database from previous failed runs
    run_hop3(f"addons:destroy {DB_NAME} --service-type postgres", check=False, show=False)

    # Show app structure
    print_header("Deploying App with Declarative PostgreSQL Provider")

    show_app_structure(
        APP_NAME,
        [
            ("app.py", "Flask application with PostgreSQL support"),
            ("requirements.txt", "Python dependencies (flask, psycopg2)"),
            ("hop3.toml", "Hop3 configuration WITH [[provider]] section"),
        ],
    )
    print_info("This demo showcases the [[provider]] section in hop3.toml.")
    print_info("The app declares its PostgreSQL requirement declaratively.")
    print_blank()
    pause(ctx.pause_between_steps)

    # Show hop3.toml - emphasize the [[provider]] section
    print_header("hop3.toml with [[provider]] Section")
    show_file_content(APP_DIR / "hop3.toml", "hop3.toml:")
    print_blank()
    print_info("Note the [[provider]] section at the end!")
    print_info("This declares that the app needs a 'postgres' addon.")
    pause(ctx.pause_between_steps)

    # Deploy the application
    print_header("Step 1: Deploy Application")
    deploy_app(ctx, APP_NAME, APP_DIR)
    set_hostname(ctx, APP_NAME, app_hostname)
    redeploy_app(ctx, APP_NAME, APP_DIR)
    wait_for_app(seconds=5, message="Waiting for application to start...")
    check_app_status(ctx, APP_NAME)

    # Test main endpoint
    print_header("Step 2: Test Application (Without Database)")
    test_app_via_curl(ctx, app_url, expected_content="Welcome to demo33")
    pause(ctx.pause_between_steps)

    # Test database status - should show not_configured
    print_header("Step 3: Check Database Status (Before Addon)")
    print_step("Testing /db-status endpoint...")
    test_app_via_curl(ctx, f"{app_url}/db-status", expected_content="not_configured")
    print_blank()
    print_info("The [[provider]] section declared the need for PostgreSQL,")
    print_info("but the addon hasn't been provisioned yet.")
    pause(ctx.pause_between_steps)

    # Create PostgreSQL addon (manual for now)
    print_header("Step 4: Provision PostgreSQL (Manual)")
    print_info("In the future, this will be automatic based on [[provider]].")
    print_info("For now, we create the addon manually:")
    print_blank()
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
        print_success("App connected to PostgreSQL!")
        pause(ctx.pause_between_steps)

        # Test database operations
        print_header("Step 8: Test Database Operations")
        print_step("Testing /db-test endpoint...")
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
        print_header("PostgreSQL Not Available")
        print_info("The [[provider]] section would enable automatic provisioning")
        print_info("once that feature is implemented.")
        print_blank()
        pause(ctx.pause_between_steps)

    # Cleanup app
    cleanup_app(ctx, APP_NAME, app_url)

    print_blank()
    print_header("Summary: [[provider]] Section")
    print_info("This demo showed the declarative [[provider]] section:")
    print_info("  [[provider]]")
    print_info('  name = "postgres"')
    print_info('  plan = "standard"')
    print_blank()
    print_info("Benefits of declarative providers:")
    print_info("  - Documents app requirements in hop3.toml")
    print_info("  - Enables future automatic provisioning")
    print_info("  - Marketplace displays required services")
    print_blank()

    if postgres_available:
        print_success("Demo 33 completed: Declarative PostgreSQL provider demonstrated.")
    else:
        print_success("Demo 33 completed: [[provider]] section showcased (PostgreSQL unavailable).")
