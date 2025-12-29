# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 56: Shlink URL Shortener.

Demonstrates deploying Shlink, a self-hosted URL shortener.
Uses SQLite by default for demo simplicity (production would use PostgreSQL).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 56: Shlink URL Shortener"
DESCRIPTION = """
Demonstrates Shlink deployment with Hop3:
  - Self-hosted URL shortener
  - PHP/Mezzio backend
  - SQLite database (demo mode)
  - REST API for programmatic access
"""

APP_NAME = "demo56"
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

    app_hostname = ctx.get_app_hostname(APP_NAME)
    app_url = f"https://{app_hostname}"

    # Ensure Docker is available
    ensure_docker(ctx)
    pause(ctx.pause_between_steps)

    # Show app structure
    print_header("Deploying Shlink URL Shortener")

    show_app_structure(
        APP_NAME,
        [
            ("Dockerfile", "Container image definition"),
            ("start.sh", "Startup script with migrations"),
            ("hop3.toml", "Hop3 configuration"),
        ],
    )
    print_info("Shlink is a modern URL shortener with REST API and analytics.")
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
    print_info("Building Docker image...")
    deploy_app(ctx, APP_NAME, APP_DIR)
    set_hostname(ctx, APP_NAME, app_hostname)
    redeploy_app(ctx, APP_NAME, APP_DIR)
    wait_for_app(seconds=10, message="Waiting for Shlink to start...")
    check_app_status(ctx, APP_NAME)

    # Test main endpoint
    print_header("Step 2: Test Application")
    test_app_via_curl(ctx, app_url, expected_content="Shlink")
    pause(ctx.pause_between_steps)

    # Test health check
    print_header("Step 3: Health Check")
    print_step("Testing /rest/health endpoint...")
    test_app_via_curl(ctx, f"{app_url}/rest/health", expected_content="pass")
    print_success("Shlink is healthy!")
    pause(ctx.pause_between_steps)

    # Cleanup
    cleanup_app(ctx, APP_NAME, app_url)
    print_success("Demo 56 completed: Shlink URL Shortener deployment demonstrated.")
