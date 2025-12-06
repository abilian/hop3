# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 3: Static Site Deployment.

Demonstrates deploying a static website with Hop3.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 3: Static Site"
DESCRIPTION = """
Demonstrates deploying a static website with Hop3:
  - Static files served directly by Nginx
  - No application server needed
  - Procfile with 'static: <directory>' directive
"""

APP_NAME = "static-site"
APP_DIR = Path(__file__).parent / "static-site"
DEFAULT_HOSTNAME = "a3.hop.demo"


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

    app_hostname = DEFAULT_HOSTNAME
    app_url = f"https://{app_hostname}"

    # Show app structure
    print_header("Deploying Static Site")

    show_app_structure(
        APP_NAME,
        [
            ("Procfile", "Defines static file directory"),
            ("public/", "Static files directory"),
            ("public/index.html", "HTML content"),
        ],
    )
    print_info("Static sites use the 'static: <dir>' Procfile directive.")
    print_blank()
    pause(ctx.pause_between_steps)

    # Show Procfile
    show_file_content(APP_DIR / "Procfile", "Procfile:")
    pause(ctx.pause_between_steps)

    # Show index.html
    show_file_content(APP_DIR / "public" / "index.html", "public/index.html:")
    pause(ctx.pause_between_steps)

    # Deploy the application
    deploy_app(ctx, APP_NAME, APP_DIR)

    # Set hostname
    set_hostname(ctx, APP_NAME, app_hostname)

    # Redeploy to apply hostname
    redeploy_app(ctx, APP_NAME, APP_DIR)

    # Wait for app
    wait_for_app(seconds=2)

    # Check status
    check_app_status(ctx, APP_NAME)

    # Test application
    print_header("Testing Application")

    test_app_via_hop3(ctx, APP_NAME, app_url)
    test_app_via_curl(ctx, app_url, expected_content="Hello World")

    # Demo app management
    print_header("Application Management")

    list_apps(ctx)
    restart_app(ctx, APP_NAME, wait_seconds=1)

    # Cleanup
    cleanup_app(ctx, APP_NAME, app_url)
