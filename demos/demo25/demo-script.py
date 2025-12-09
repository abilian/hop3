# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 25: OpenCloud.

Demonstrates deploying OpenCloud, a modern file sharing and collaboration
platform, with Docker. Uses file-based storage (no database needed).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 25: OpenCloud"
DESCRIPTION = """
Demonstrates deploying OpenCloud with Hop3:
  - Docker-based deployment
  - File-based storage (no database needed)
  - Modern file sharing platform
  - Similar to Nextcloud/ownCloud
"""

APP_NAME = "demo25"
APP_DIR = Path(__file__).parent / "app"
DEFAULT_HOSTNAME = "demo25.hop"


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
    print_header("Deploying OpenCloud")

    show_app_structure(
        APP_NAME,
        [
            ("Dockerfile", "Docker image with OpenCloud"),
            ("start.sh", "Startup script"),
            ("hop3.toml", "Hop3 configuration"),
        ],
    )
    print_info("OpenCloud is a modern file sharing and collaboration platform.")
    print_info("It doesn't require a database - all data is stored in files.")
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
    wait_for_app(seconds=15, message="Waiting for OpenCloud to start...")
    check_app_status(ctx, APP_NAME)
    pause(ctx.pause_between_steps)

    # Test main endpoint (OpenCloud login page)
    print_header("Step 3: Test Application")
    print_step("Testing OpenCloud main page...")
    test_app_via_curl(ctx, app_url, expected_content="OpenCloud")
    print_success("OpenCloud is accessible!")
    pause(ctx.pause_between_steps)

    # Cleanup
    print_header("Step 4: Cleanup")
    cleanup_app(ctx, APP_NAME, app_url)
    print_success("Demo 25 completed: OpenCloud deployed successfully.")
