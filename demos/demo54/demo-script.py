# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 54: Miniflux RSS Reader.

Demonstrates deploying Miniflux, a minimalist RSS reader with PostgreSQL.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 54: Miniflux RSS Reader"
DESCRIPTION = """
Demonstrates Miniflux deployment with Hop3:
  - Minimalist RSS/Atom feed reader
  - PostgreSQL for data storage
  - Single Go binary
  - Full-text search powered by PostgreSQL
"""

APP_NAME = "demo54"
APP_DIR = Path(__file__).parent / "app"

# This demo requires Docker daemon for building/deploying containers
REQUIRES = ["docker"]
PG_NAME = "demo54-db"


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
    run_hop3(f"addon destroy {PG_NAME} --service-type postgres", check=False, show=False)

    # Show app structure
    print_header("Deploying Miniflux RSS Reader")

    show_app_structure(
        APP_NAME,
        [
            ("Dockerfile", "Container image definition"),
            ("start.sh", "Startup script"),
            ("hop3.toml", "Hop3 configuration with PostgreSQL"),
        ],
    )
    print_info("Miniflux is a minimalist feed reader - single binary + PostgreSQL.")
    print_blank()
    pause(ctx.pause_between_steps)

    # Show Dockerfile
    show_file_content(APP_DIR / "Dockerfile", "Dockerfile:")
    pause(ctx.pause_between_steps)

    # Show hop3.toml
    show_file_content(APP_DIR / "hop3.toml", "hop3.toml:")
    pause(ctx.pause_between_steps)

    # Deploy the application (without PostgreSQL first)
    print_header("Step 1: Deploy Application")
    print_info("Building Docker image...")
    deploy_app(ctx, APP_NAME, APP_DIR)
    set_hostname(ctx, APP_NAME, app_hostname)
    pause(ctx.pause_between_steps)

    # Create PostgreSQL addon
    print_header("Step 2: Create PostgreSQL Database")
    print_step(f"Creating PostgreSQL instance '{PG_NAME}'...")
    result = run_hop3(f"addon create postgres {PG_NAME}", check=False)

    pg_available = result.returncode == 0
    if not pg_available:
        print_warning("PostgreSQL creation failed.")
        if result.stderr:
            print_info(f"  Error: {result.stderr.strip()}")
        msg = "PostgreSQL addon creation failed"
        raise RuntimeError(msg)

    print_success(f"PostgreSQL instance '{PG_NAME}' created.")
    pause(ctx.pause_between_steps)

    # Attach PostgreSQL to app
    print_header("Step 3: Attach PostgreSQL to Application")
    print_step(f"Attaching '{PG_NAME}' to '{APP_NAME}'...")
    result = run_hop3(
        f"addon attach {PG_NAME} --app {APP_NAME} --service-type postgres",
        check=False,
    )

    if result.returncode != 0:
        print_warning("Failed to attach PostgreSQL.")
        if result.stderr:
            print_info(f"  Error: {result.stderr.strip()}")
        msg = "PostgreSQL addon attach failed"
        raise RuntimeError(msg)

    print_success("PostgreSQL attached. DATABASE_URL is now set.")
    pause(ctx.pause_between_steps)

    # Redeploy to pick up DATABASE_URL
    print_header("Step 4: Redeploy with Database")
    print_step("Redeploying container with DATABASE_URL...")
    redeploy_app(ctx, APP_NAME, APP_DIR)
    wait_for_app(seconds=10, message="Waiting for Miniflux to start and run migrations...")
    check_app_status(ctx, APP_NAME)

    # Test main endpoint
    print_header("Step 5: Test Application")
    test_app_via_curl(ctx, app_url, expected_content="Miniflux")
    pause(ctx.pause_between_steps)

    # Test health check endpoint
    print_header("Step 6: Health Check")
    print_step("Testing /healthcheck endpoint...")
    test_app_via_curl(ctx, f"{app_url}/healthcheck", expected_content="OK")
    print_success("Miniflux is healthy!")
    pause(ctx.pause_between_steps)

    # Test version endpoint
    print_header("Step 7: Version Info")
    print_step("Testing /version endpoint...")
    test_app_via_curl(ctx, f"{app_url}/version", expected_content="2.")
    print_success("Version information available!")
    pause(ctx.pause_between_steps)

    # Cleanup PostgreSQL
    print_header("Step 8: Cleanup PostgreSQL")
    print_step("Detaching and destroying PostgreSQL...")
    run_hop3(
        f"addon detach {PG_NAME} --app {APP_NAME} --service-type postgres",
        check=False,
    )
    run_hop3(f"addon destroy {PG_NAME} --service-type postgres", check=False)
    print_success("PostgreSQL cleaned up.")
    pause(ctx.pause_between_steps)

    # Cleanup app
    cleanup_app(ctx, APP_NAME, app_url)
    print_success("Demo 54 completed: Miniflux RSS Reader deployment demonstrated.")
