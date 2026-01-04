# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 25: Filebrowser.

Demonstrates deploying Filebrowser, a simple web-based file browser,
with Docker. Uses file-based storage (no database needed).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 25: Filebrowser"
DESCRIPTION = """
Demonstrates deploying Filebrowser with Hop3:
  - Docker-based deployment
  - File-based storage (no database needed)
  - Simple web-based file management
  - Default credentials: admin / admin
"""

APP_NAME = "demo25"
APP_DIR = Path(__file__).parent / "app"

# This demo requires Docker daemon for building/deploying containers
REQUIRES = ["docker"]


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
    print_header("Deploying Filebrowser")

    show_app_structure(
        APP_NAME,
        [
            ("Dockerfile", "Docker image with Filebrowser"),
            ("start.sh", "Startup script"),
            ("hop3.toml", "Hop3 configuration"),
        ],
    )
    print_info("Filebrowser is a simple web-based file browser.")
    print_info("Default credentials: admin / admin")
    print_blank()
    pause(ctx.pause_between_steps)

    # Show Dockerfile
    show_file_content(APP_DIR / "Dockerfile", "Dockerfile:")
    pause(ctx.pause_between_steps)

    # Deploy the application
    print_header("Step 1: Deploy Application")
    print_info("Building Docker image...")
    deploy_app(ctx, APP_NAME, APP_DIR)
    set_hostname(ctx, APP_NAME, app_hostname)
    pause(ctx.pause_between_steps)

    # Redeploy to apply hostname configuration (generates nginx config)
    print_header("Step 2: Redeploy with Hostname")
    redeploy_app(ctx, APP_NAME, APP_DIR)
    wait_for_app(seconds=10, message="Waiting for Filebrowser to start...")
    check_app_status(ctx, APP_NAME)
    pause(ctx.pause_between_steps)

    # Test main endpoint (Filebrowser login page)
    print_header("Step 3: Test Application")
    print_step("Testing Filebrowser login page...")
    test_app_via_curl(ctx, f"{app_url}/login", expected_content="File Browser")
    print_success("Filebrowser is accessible!")
    pause(ctx.pause_between_steps)

    # Cleanup
    print_header("Step 4: Cleanup")
    cleanup_app(ctx, APP_NAME, app_url)
    print_success("Demo 25 completed: Filebrowser deployed successfully.")
