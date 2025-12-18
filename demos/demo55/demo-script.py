# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 55: Linkding Bookmark Manager.

Demonstrates deploying Linkding, a self-hosted bookmark manager with PostgreSQL.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 55: Linkding Bookmark Manager"
DESCRIPTION = """
Demonstrates Linkding deployment with Hop3:
  - Self-hosted bookmark manager
  - Django/Python backend
  - PostgreSQL for data storage
  - Tag-based organization
"""

APP_NAME = "demo55"
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
    print_header("Deploying Linkding Bookmark Manager")

    show_app_structure(
        APP_NAME,
        [
            ("Dockerfile", "Container image definition"),
            ("start.sh", "Startup script with migrations"),
            ("hop3.toml", "Hop3 configuration with PostgreSQL"),
        ],
    )
    print_info("Linkding is a minimal bookmark manager with tagging support.")
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
    wait_for_app(seconds=15, message="Waiting for Linkding to build and start...")
    check_app_status(ctx, APP_NAME)

    # Test main endpoint
    print_header("Step 2: Test Application")
    test_app_via_curl(ctx, app_url, expected_content="linkding")
    pause(ctx.pause_between_steps)

    # Test login page
    print_header("Step 3: Login Page")
    print_step("Testing login endpoint...")
    test_app_via_curl(ctx, f"{app_url}/login/", expected_content="Login")
    print_success("Login page accessible!")
    pause(ctx.pause_between_steps)

    # Test health check
    print_header("Step 4: Health Check")
    print_step("Testing /health endpoint...")
    test_app_via_curl(ctx, f"{app_url}/health/", expected_content="ok")
    print_success("Linkding is healthy!")
    pause(ctx.pause_between_steps)

    # Cleanup
    cleanup_app(ctx, APP_NAME, app_url)
    print_success("Demo 55 completed: Linkding Bookmark Manager deployment demonstrated.")
