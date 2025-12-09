# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 24: Listmonk.

Demonstrates deploying Listmonk, a high-performance newsletter and mailing list
manager, with Docker and PostgreSQL addon.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 24: Listmonk"
DESCRIPTION = """
Demonstrates deploying Listmonk with Hop3:
  - Docker-based deployment
  - PostgreSQL addon for data storage
  - Newsletter and mailing list management
  - High-performance Go application
"""

APP_NAME = "demo24"
APP_DIR = Path(__file__).parent / "app"
DEFAULT_HOSTNAME = "demo24.hop"
POSTGRES_NAME = "demo24-db"


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
    from lib.server import ensure_docker

    app_hostname = DEFAULT_HOSTNAME
    app_url = f"https://{app_hostname}"

    # Ensure Docker is available
    ensure_docker(ctx)
    pause(ctx.pause_between_steps)

    # Clean up any leftover PostgreSQL addon from previous failed runs
    run_hop3(f"addons:destroy {POSTGRES_NAME} --service-type postgres", check=False, show=False)

    # Show app structure
    print_header("Deploying Listmonk")

    show_app_structure(
        APP_NAME,
        [
            ("Dockerfile", "Docker image with Listmonk"),
            ("start.sh", "Startup script"),
            ("hop3.toml", "Hop3 configuration"),
        ],
    )
    print_info("Listmonk is a high-performance newsletter and mailing list manager.")
    print_info("Written in Go, it's self-hosted and privacy-focused.")
    print_blank()
    pause(ctx.pause_between_steps)

    # Show Dockerfile
    show_file_content(APP_DIR / "Dockerfile", "Dockerfile:")
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
    wait_for_app(seconds=20, message="Waiting for Listmonk to initialize database...")
    check_app_status(ctx, APP_NAME)

    # Test main endpoint (Listmonk login page)
    print_header("Step 5: Test Application")
    test_app_via_curl(ctx, app_url, expected_content="listmonk")
    print_success("Listmonk is running!")
    pause(ctx.pause_between_steps)

    # Test health endpoint (public endpoint at /health)
    print_header("Step 6: Health Check")
    test_app_via_curl(ctx, f"{app_url}/health", expected_content="true")
    print_success("Health check passed!")
    pause(ctx.pause_between_steps)

    # Cleanup
    print_header("Step 7: Cleanup")
    print_step("Detaching and destroying PostgreSQL...")
    run_hop3(
        f"addons:detach {POSTGRES_NAME} --app {APP_NAME} --service-type postgres",
        check=False,
    )
    run_hop3(f"addons:destroy {POSTGRES_NAME} --service-type postgres", check=False)
    print_success("PostgreSQL cleaned up.")

    cleanup_app(ctx, APP_NAME, app_url)
    print_success("Demo 24 completed: Listmonk deployed successfully.")
