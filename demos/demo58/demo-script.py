# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 58: Static Site (Jekyll-style) Prerequisite Test.

Tests static site deployment on the server.
This helps verify prerequisites for Jekyll/Hugo deployments.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 58: Static Site Prerequisite Test"
DESCRIPTION = """
Tests static site deployment:
  - Pre-built HTML content
  - Nginx static file serving
  - Basic health endpoint
"""

APP_NAME = "demo58"
APP_DIR = Path(__file__).parent / "app"


def run(ctx: DemoContext) -> None:
    """Run the demo."""
    from lib import (
        check_app_status,
        cleanup_app,
        deploy_app,
        pause,
        print_header,
        print_info,
        print_success,
        redeploy_app,
        set_hostname,
        show_app_structure,
        show_file_content,
        test_app_via_curl,
        wait_for_app,
    )

    app_hostname = ctx.get_app_hostname(APP_NAME)
    app_url = f"https://{app_hostname}"

    # Show app structure
    print_header("Testing Static Site Prerequisites")

    show_app_structure(
        APP_NAME,
        [
            ("_site/index.html", "Static homepage"),
            ("_site/up.html", "Health check page"),
            ("hop3.toml", "Hop3 configuration"),
        ],
    )
    print_info("This demo verifies static site serving for Jekyll/Hugo deployments.")
    pause(ctx.pause_between_steps)

    # Show hop3.toml
    show_file_content(APP_DIR / "hop3.toml", "hop3.toml:")
    pause(ctx.pause_between_steps)

    # Deploy the application
    print_header("Step 1: Deploy Static Site")
    deploy_app(ctx, APP_NAME, APP_DIR)
    set_hostname(ctx, APP_NAME, app_hostname)
    redeploy_app(ctx, APP_NAME, APP_DIR)
    wait_for_app(seconds=3, message="Waiting for static site to be ready...")
    check_app_status(ctx, APP_NAME)

    # Test main endpoint
    print_header("Step 2: Test Homepage")
    test_app_via_curl(ctx, app_url, expected_content="Static Site")
    pause(ctx.pause_between_steps)

    # Test health check
    print_header("Step 3: Health Check")
    test_app_via_curl(ctx, f"{app_url}/up.html", expected_content="OK")
    print_success("Static site prerequisites verified!")
    pause(ctx.pause_between_steps)

    # Cleanup
    cleanup_app(ctx, APP_NAME, app_url)
    print_success("Demo 58 completed: Static site prerequisites test passed.")
