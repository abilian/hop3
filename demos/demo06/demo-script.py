# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 6: Ruby Sinatra Deployment.

Demonstrates deploying a Ruby/Sinatra application with Hop3.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 6: Ruby Sinatra"
DESCRIPTION = """
Demonstrates deploying a Ruby application with Hop3:
  - Sinatra microframework
  - Bundler for dependency management
  - Automatic bundle install during deployment
"""

APP_NAME = "demo06"
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
    print_header("Deploying Ruby/Sinatra Application")

    show_app_structure(
        APP_NAME,
        [
            ("app.rb", "Sinatra application"),
            ("Gemfile", "Ruby dependencies"),
            ("Gemfile.lock", "Locked versions"),
            ("Procfile", "Process definition"),
        ],
    )
    print_info("Ruby apps are detected by Gemfile.")
    print_blank()
    pause(ctx.pause_between_steps)

    # Show app.rb
    show_file_content(APP_DIR / "app.rb", "app.rb (Sinatra application):")
    pause(ctx.pause_between_steps)

    # Show Gemfile
    show_file_content(APP_DIR / "Gemfile", "Gemfile:")
    pause(ctx.pause_between_steps)

    # Deploy the application
    print_info("Hop3 will run 'bundle install' automatically.")
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
    test_app_via_curl(ctx, app_url, expected_content="Welcome to demo06")

    # Demo app management
    print_header("Application Management")

    list_apps(ctx)
    restart_app(ctx, APP_NAME, wait_seconds=2)

    # Cleanup
    cleanup_app(ctx, APP_NAME, app_url)
