# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 49: Taiga.

Demonstrates deploying Taiga, an agile project management
platform, with Docker and PostgreSQL addon.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 49: Taiga"
DESCRIPTION = """
Demonstrates deploying Taiga with Hop3:
  - Docker-based deployment
  - PostgreSQL addon for data storage
  - Agile project management (Scrum/Kanban)
  - Open-source Jira/Trello alternative
"""

APP_NAME = "demo49"
APP_DIR = Path(__file__).parent / "app"

# This demo requires Docker daemon for building/deploying containers
REQUIRES = ["docker"]
POSTGRES_NAME = "demo49-db"


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
    from lib.server import ensure_docker, ensure_postgres

    app_hostname = ctx.get_app_hostname(APP_NAME)
    app_url = f"https://{app_hostname}"

    # Ensure Docker and PostgreSQL are available
    ensure_docker(ctx)
    ensure_postgres(ctx)
    pause(ctx.pause_between_steps)

    # Clean up any leftover PostgreSQL addon from previous failed runs
    run_hop3(f"addon destroy {POSTGRES_NAME} --service-type postgres", check=False, show=False)

    # Show app structure
    print_header("Deploying Taiga")

    show_app_structure(
        APP_NAME,
        [
            ("Dockerfile", "Combined backend + frontend image"),
            ("nginx.conf", "Nginx config for frontend + API proxy"),
            ("start.sh", "Startup script with PostgreSQL configuration"),
            ("hop3.toml", "Hop3 configuration with [[provider]] section"),
        ],
    )
    print_info("Taiga is an agile project management platform.")
    print_info("Features Scrum, Kanban, issue tracking, and wiki.")
    print_blank()
    pause(ctx.pause_between_steps)

    # Show hop3.toml
    show_file_content(APP_DIR / "hop3.toml", "hop3.toml:")
    pause(ctx.pause_between_steps)

    # Create PostgreSQL addon
    print_header("Step 1: Create PostgreSQL Database")
    print_step(f"Creating PostgreSQL instance '{POSTGRES_NAME}'...")
    result = run_hop3(f"addon create postgres {POSTGRES_NAME}", check=False)

    if result.returncode != 0:
        print_warning("PostgreSQL creation failed.")
        if result.stderr:
            print_info(f"  Error: {result.stderr.strip()}")
        cleanup_app(ctx, APP_NAME, app_url)
        return

    print_success(f"PostgreSQL instance '{POSTGRES_NAME}' created.")
    pause(ctx.pause_between_steps)

    # Deploy the application
    print_header("Step 2: Deploy Application")
    print_info("Building Docker image (this may take a while)...")
    deploy_app(ctx, APP_NAME, APP_DIR)
    set_hostname(ctx, APP_NAME, app_hostname)

    # Attach PostgreSQL addon
    print_header("Step 3: Attach PostgreSQL")
    print_step(f"Attaching '{POSTGRES_NAME}' to '{APP_NAME}'...")
    result = run_hop3(
        f"addon attach {POSTGRES_NAME} --app {APP_NAME} --service-type postgres",
        check=False,
    )
    if result.returncode != 0:
        print_warning("Failed to attach PostgreSQL.")
    else:
        print_success("PostgreSQL attached. Database env vars are now set.")
    pause(ctx.pause_between_steps)

    # Redeploy with database
    print_header("Step 4: Redeploy with Database")
    redeploy_app(ctx, APP_NAME, APP_DIR)
    # Taiga needs time to run migrations on first start
    wait_for_app(seconds=45, message="Waiting for Taiga to start and run migrations...")
    check_app_status(ctx, APP_NAME)

    # Test main endpoint
    print_header("Step 5: Test Application")
    # Taiga shows login page
    test_app_via_curl(ctx, app_url, expected_content="Taiga")
    print_success("Taiga is running!")
    print_blank()
    print_info("Default login: admin / admin123")
    pause(ctx.pause_between_steps)

    # Cleanup
    print_header("Step 6: Cleanup")
    print_step("Detaching and destroying PostgreSQL...")
    run_hop3(
        f"addon detach {POSTGRES_NAME} --app {APP_NAME} --service-type postgres",
        check=False,
    )
    run_hop3(f"addon destroy {POSTGRES_NAME} --service-type postgres", check=False)
    print_success("PostgreSQL cleaned up.")

    cleanup_app(ctx, APP_NAME, app_url)
    print_success("Demo 49 completed: Taiga deployed successfully.")
