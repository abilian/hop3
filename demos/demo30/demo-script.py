# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 30: Native Python Deployment.

Demonstrates deploying a native Python application with Hop3.
This is the native equivalent of demo02 (Docker Deployment).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 30: Native Python Deployment"
DESCRIPTION = """
Demonstrates deploying a native Python application with Hop3:
  - Building with native Python builder
  - Installing dependencies from requirements.txt
  - Running with gunicorn
  - Routing traffic through nginx proxy
"""

APP_NAME = "demo30"
APP_DIR = Path(__file__).parent / "app"


def run(ctx: DemoContext) -> None:
    """Run the demo."""
    from lib import (
        check_app_status,
        cleanup_app,
        deploy_app,
        list_apps,
        pause,
        print_blank,
        print_header,
        print_info,
        redeploy_app,
        restart_app,
        set_hostname,
        show_app_structure,
        show_file_content,
        test_app_via_curl,
        test_app_via_hop3,
        wait_for_app,
    )

    app_hostname = ctx.hostname
    app_url = f"https://{app_hostname}"

    # Show app structure
    print_header("Deploying Native Python Application")

    show_app_structure(
        APP_NAME,
        [
            ("app.py", "Flask application"),
            ("requirements.txt", "Python dependencies"),
            ("hop3.toml", "Hop3 configuration (native Python builder)"),
        ],
    )
    print_info("Note: This uses native Python deployment, not Docker.")
    print_info("The app runs directly on the server with gunicorn.")
    print_blank()
    pause(ctx.pause_between_steps)

    # Show hop3.toml
    show_file_content(APP_DIR / "hop3.toml", "Hop3 configuration (hop3.toml):")
    pause(ctx.pause_between_steps)

    # Deploy the application
    print_info("This will: 1) Create virtualenv, 2) Install dependencies, 3) Start gunicorn")
    deploy_app(ctx, APP_NAME, APP_DIR)

    # Set hostname
    set_hostname(ctx, APP_NAME, app_hostname)

    # Redeploy to apply hostname
    redeploy_app(ctx, APP_NAME, APP_DIR)

    # Wait for app to start
    wait_for_app(seconds=5, message="Waiting for application to start...")

    # Verify deployment
    check_app_status(ctx, APP_NAME)

    # Test application
    print_header("Testing Application")

    test_app_via_hop3(ctx, APP_NAME, app_url)
    test_app_via_curl(ctx, app_url, expected_content="Welcome to demo30")

    # Demo app management
    print_header("Application Management")

    list_apps(ctx)
    check_app_status(ctx, APP_NAME)
    restart_app(ctx, APP_NAME, wait_seconds=3)

    # Cleanup
    cleanup_app(ctx, APP_NAME, app_url)
