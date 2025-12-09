# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 22: Radicale CalDAV/CardDAV Server.

Demonstrates deploying Radicale, a simple calendar and contact server,
with Docker. No database required - uses file-based storage.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 22: Radicale CalDAV/CardDAV"
DESCRIPTION = """
Demonstrates deploying Radicale with Hop3:
  - Docker-based deployment
  - File-based storage (no database needed)
  - CalDAV/CardDAV server for calendars and contacts
  - Simple htpasswd authentication
"""

APP_NAME = "demo22"
APP_DIR = Path(__file__).parent / "app"
DEFAULT_HOSTNAME = "demo22.hop"


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

    app_hostname = DEFAULT_HOSTNAME
    app_url = f"https://{app_hostname}"

    # Ensure Docker is available
    ensure_docker(ctx)
    pause(ctx.pause_between_steps)

    # Show app structure
    print_header("Deploying Radicale CalDAV/CardDAV Server")

    show_app_structure(
        APP_NAME,
        [
            ("Dockerfile", "Docker image with Radicale"),
            ("start.sh", "Startup script"),
            ("hop3.toml", "Hop3 configuration"),
            ("rights", "Access rights configuration"),
        ],
    )
    print_info("Radicale is a simple CalDAV/CardDAV server for calendars and contacts.")
    print_info("No database required - uses file-based storage.")
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
    wait_for_app(seconds=10, message="Waiting for Radicale to start...")
    check_app_status(ctx, APP_NAME)
    pause(ctx.pause_between_steps)

    # Test main endpoint (Radicale web interface)
    # Radicale redirects / to /.web/, so test the web interface directly
    print_header("Step 3: Test Application")
    print_step("Testing Radicale web interface...")
    test_app_via_curl(ctx, f"{app_url}/.web/", expected_content="Radicale")
    print_success("Radicale web interface is accessible!")
    pause(ctx.pause_between_steps)

    # Cleanup
    print_header("Step 4: Cleanup")
    cleanup_app(ctx, APP_NAME, app_url)
    print_success("Demo 22 completed: Radicale deployed successfully.")
