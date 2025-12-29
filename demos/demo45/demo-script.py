# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 45: Minimal Ruby/Sinatra with PostgreSQL.

Tests Ruby + PostgreSQL connectivity to validate hypothesis
that MySQL SSL issue is Ruby/mysql2 specific.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 45: Ruby/Sinatra + PostgreSQL"
DESCRIPTION = """
Demonstrates minimal Ruby app with PostgreSQL:
  - Docker-based deployment
  - PostgreSQL addon for data storage
  - Tests Ruby + PostgreSQL connectivity
"""

APP_NAME = "demo45"
APP_DIR = Path(__file__).parent / "app"
POSTGRES_NAME = "demo45-db"


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
    run_hop3(f"addons:destroy {POSTGRES_NAME} --service-type postgres", check=False, show=False)

    # Show app structure
    print_header("Deploying Ruby/Sinatra + PostgreSQL")

    show_app_structure(
        APP_NAME,
        [
            ("Dockerfile", "Docker image based on ruby:3.2-alpine"),
            ("app.rb", "Sinatra app with PostgreSQL connection"),
            ("hop3.toml", "Hop3 configuration with [[provider]] section"),
        ],
    )
    print_info("This is a minimal test to verify Ruby + PostgreSQL works.")
    print_blank()
    pause(ctx.pause_between_steps)

    # Show hop3.toml
    show_file_content(APP_DIR / "hop3.toml", "hop3.toml:")
    pause(ctx.pause_between_steps)

    # Create PostgreSQL addon
    print_header("Step 1: Create PostgreSQL Database")
    print_step(f"Creating PostgreSQL instance '{POSTGRES_NAME}'...")
    result = run_hop3(f"addons:create postgres {POSTGRES_NAME}", check=False)

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
    print_info("Building Docker image...")
    deploy_app(ctx, APP_NAME, APP_DIR)
    set_hostname(ctx, APP_NAME, app_hostname)

    # Attach PostgreSQL addon
    print_header("Step 3: Attach PostgreSQL")
    print_step(f"Attaching '{POSTGRES_NAME}' to '{APP_NAME}'...")
    result = run_hop3(
        f"addons:attach {POSTGRES_NAME} --app {APP_NAME} --service-type postgres",
        check=False,
    )
    if result.returncode != 0:
        print_warning("Failed to attach PostgreSQL.")
    else:
        print_success("PostgreSQL attached. DATABASE_URL is now set.")
    pause(ctx.pause_between_steps)

    # Redeploy with database
    print_header("Step 4: Redeploy with Database")
    redeploy_app(ctx, APP_NAME, APP_DIR)
    wait_for_app(seconds=15, message="Waiting for Sinatra to start...")
    check_app_status(ctx, APP_NAME)

    # Test main endpoint
    print_header("Step 5: Test Application")
    test_app_via_curl(ctx, app_url, expected_content="Ruby/Sinatra")
    print_success("App is running!")
    print_blank()
    pause(ctx.pause_between_steps)

    # Cleanup
    print_header("Step 6: Cleanup")
    print_step("Detaching and destroying PostgreSQL...")
    run_hop3(
        f"addons:detach {POSTGRES_NAME} --app {APP_NAME} --service-type postgres",
        check=False,
    )
    run_hop3(f"addons:destroy {POSTGRES_NAME} --service-type postgres", check=False)
    print_success("PostgreSQL cleaned up.")

    cleanup_app(ctx, APP_NAME, app_url)
    print_success("Demo 45 completed: Ruby/Sinatra + PostgreSQL works!")
