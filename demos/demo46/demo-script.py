# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 46: Minimal PHP with MySQL.

Tests PHP + MySQL connectivity to compare with Ruby/mysql2.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 46: PHP + MySQL"
DESCRIPTION = """
Demonstrates minimal PHP app with MySQL:
  - Docker-based deployment
  - MySQL addon for data storage
  - Tests PHP + MySQL connectivity
"""

APP_NAME = "demo46"
APP_DIR = Path(__file__).parent / "app"

# This demo requires Docker daemon for building/deploying containers
REQUIRES = ["docker"]
MYSQL_NAME = "demo46-db"


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

    app_hostname = ctx.get_app_hostname(APP_NAME)
    app_url = f"https://{app_hostname}"

    # Ensure Docker and MySQL are available
    ensure_docker(ctx)
    ensure_mysql(ctx)
    pause(ctx.pause_between_steps)

    # Clean up any leftover MySQL addon from previous failed runs
    run_hop3(f"addon destroy {MYSQL_NAME} --service-type mysql -y", check=False, show=False)

    # Show app structure
    print_header("Deploying PHP + MySQL")

    show_app_structure(
        APP_NAME,
        [
            ("Dockerfile", "Docker image based on php:8.3-apache"),
            ("index.php", "PHP app with MySQL connection test"),
            ("hop3.toml", "Hop3 configuration with [[provider]] section"),
        ],
    )
    print_info("This is a minimal test to verify PHP + MySQL works.")
    print_blank()
    pause(ctx.pause_between_steps)

    # Show hop3.toml
    show_file_content(APP_DIR / "hop3.toml", "hop3.toml:")
    pause(ctx.pause_between_steps)

    # Create MySQL addon
    print_header("Step 1: Create MySQL Database")
    print_step(f"Creating MySQL instance '{MYSQL_NAME}'...")
    result = run_hop3(f"addon create mysql {MYSQL_NAME}", check=False)

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
        f"addon attach {MYSQL_NAME} --app {APP_NAME} --service-type mysql",
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
    wait_for_app(seconds=10, message="Waiting for Apache to start...")
    check_app_status(ctx, APP_NAME)

    # Test main endpoint
    print_header("Step 5: Test Application")
    test_app_via_curl(ctx, app_url, expected_content="PHP + MySQL")
    print_success("App is running!")
    print_blank()
    pause(ctx.pause_between_steps)

    # Cleanup
    print_header("Step 6: Cleanup")
    print_step("Detaching and destroying MySQL...")
    run_hop3(
        f"addon detach {MYSQL_NAME} --app {APP_NAME} --service-type mysql",
        check=False,
    )
    run_hop3(f"addon destroy {MYSQL_NAME} --service-type mysql -y", check=False)
    print_success("MySQL cleaned up.")

    cleanup_app(ctx, APP_NAME, app_url)
    print_success("Demo 46 completed: PHP + MySQL works!")
