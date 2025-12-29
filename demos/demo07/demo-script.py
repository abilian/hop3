# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 7: Flask with Gunicorn.

Demonstrates deploying a Flask app with explicit Gunicorn configuration.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 7: Flask + Gunicorn"
DESCRIPTION = """
Demonstrates Flask with explicit Gunicorn server:
  - Gunicorn as WSGI server (instead of default uWSGI)
  - Custom Procfile web command
  - Direct control over server configuration
"""

APP_NAME = "demo07"
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

    app_hostname = ctx.get_app_hostname(APP_NAME)
    app_url = f"https://{app_hostname}"

    # Show app structure
    print_header("Deploying Flask with Gunicorn")

    show_app_structure(
        APP_NAME,
        [
            ("app.py", "Flask application"),
            ("requirements.txt", "Python dependencies (includes gunicorn)"),
            ("Procfile", "Explicit gunicorn command"),
        ],
    )
    print_info("This demo uses Gunicorn instead of the default uWSGI.")
    print_blank()
    pause(ctx.pause_between_steps)

    # Show Procfile (key difference from demo1)
    show_file_content(APP_DIR / "Procfile", "Procfile (with explicit Gunicorn):")
    pause(ctx.pause_between_steps)

    # Show requirements.txt
    show_file_content(APP_DIR / "requirements.txt", "requirements.txt:")
    pause(ctx.pause_between_steps)

    # Deploy the application
    deploy_app(ctx, APP_NAME, APP_DIR)

    # Set hostname
    set_hostname(ctx, APP_NAME, app_hostname)

    # Redeploy to apply hostname
    redeploy_app(ctx, APP_NAME, APP_DIR)

    # Wait for app
    wait_for_app(seconds=3)

    # Check status
    check_app_status(ctx, APP_NAME)

    # Test application
    print_header("Testing Application")

    test_app_via_hop3(ctx, APP_NAME, app_url)
    test_app_via_curl(ctx, app_url, expected_content="Welcome to demo07")

    # Demo app management
    print_header("Application Management")

    list_apps(ctx)
    restart_app(ctx, APP_NAME, wait_seconds=2)

    # Cleanup
    cleanup_app(ctx, APP_NAME, app_url)
