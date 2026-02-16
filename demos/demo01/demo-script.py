# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 1: uWSGI Deployment.

Demonstrates deploying a Python/Flask application using uWSGI.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 1: uWSGI Deployment"
DESCRIPTION = """
Demonstrates deploying a Python/Flask application with Hop3:
  - Python app with requirements.txt
  - uWSGI as the application server
  - Nginx as reverse proxy
"""

APP_NAME = "demo01"
APP_DIR = Path(__file__).parent / "app"


def run(ctx: DemoContext) -> None:
    """Run the demo."""
    from lib import (
        check_app_status,
        cleanup_app,
        deploy_app,
        list_apps,
        pause,
        print_header,
        redeploy_app,
        restart_app,
        set_env_vars,
        set_hostname,
        show_app_structure,
        show_config,
        show_file_content,
        test_app_via_curl,
        test_app_via_hop3,
        wait_for_app,
        wait_for_app_ready,
    )

    # Use unique hostname per app to avoid nginx routing conflicts
    app_hostname = ctx.get_app_hostname(APP_NAME)
    app_url = f"https://{app_hostname}"

    # Show app structure
    print_header("Deploying Sample Application")

    show_app_structure(
        APP_NAME,
        [
            ("app.py", "Flask application"),
            ("requirements.txt", "Python dependencies"),
            ("hop3.toml", "Hop3 configuration"),
        ],
    )
    pause(ctx.pause_between_steps)

    # Show hop3.toml content
    show_file_content(APP_DIR / "hop3.toml", "Hop3 configuration (hop3.toml):", max_lines=15)
    pause(ctx.pause_between_steps)

    # Deploy the application
    deploy_app(ctx, APP_NAME, APP_DIR)

    # Set hostname
    set_hostname(ctx, APP_NAME, app_hostname)

    # Redeploy to apply hostname
    redeploy_app(ctx, APP_NAME, APP_DIR)

    # Wait for app to be ready (smart polling instead of fixed sleep)
    wait_for_app_ready(APP_NAME, timeout=30.0)
    # Give nginx extra time to reload after config change
    wait_for_app(seconds=2, message="Waiting for nginx to reload...")

    # Verify deployment
    check_app_status(ctx, APP_NAME)

    # Test application
    print_header("Testing Application")

    test_app_via_hop3(ctx, APP_NAME, app_url)
    test_app_via_curl(ctx, app_url, expected_content="Welcome to demo01")

    # Demo app management
    print_header("Application Management")

    list_apps(ctx)
    set_env_vars(ctx, APP_NAME, DEBUG="true", LOG_LEVEL="info")
    show_config(ctx, APP_NAME)
    restart_app(ctx, APP_NAME, wait_seconds=2)

    # Cleanup
    cleanup_app(ctx, APP_NAME, app_url)
