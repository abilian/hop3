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
        redeploy_app,
        set_hostname,
        show_app_structure,
        show_file_content,
        test_app_via_curl,
        wait_for_app,
    )
    from lib.server import ensure_docker

    app_hostname = ctx.hostname
    app_url = f"https://{app_hostname}"

    # Ensure Docker is available
    ensure_docker(ctx)
    pause(ctx.pause_between_steps)

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

    # Deploy the application
    print_header("Step 1: Deploy Application")
    print_info("Building Docker image and provisioning PostgreSQL...")
    deploy_app(ctx, APP_NAME, APP_DIR)
    set_hostname(ctx, APP_NAME, app_hostname)
    redeploy_app(ctx, APP_NAME, APP_DIR)
    wait_for_app(seconds=10, message="Waiting for Miniflux to start and run migrations...")
    check_app_status(ctx, APP_NAME)

    # Test main endpoint
    print_header("Step 2: Test Application")
    test_app_via_curl(ctx, app_url, expected_content="Miniflux")
    pause(ctx.pause_between_steps)

    # Test health check endpoint
    print_header("Step 3: Health Check")
    print_step("Testing /healthcheck endpoint...")
    test_app_via_curl(ctx, f"{app_url}/healthcheck", expected_content="OK")
    print_success("Miniflux is healthy!")
    pause(ctx.pause_between_steps)

    # Test version endpoint
    print_header("Step 4: Version Info")
    print_step("Testing /version endpoint...")
    test_app_via_curl(ctx, f"{app_url}/version", expected_content="version")
    print_success("Version information available!")
    pause(ctx.pause_between_steps)

    # Cleanup
    cleanup_app(ctx, APP_NAME, app_url)
    print_success("Demo 54 completed: Miniflux RSS Reader deployment demonstrated.")
