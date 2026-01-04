# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 57: Ruby/Sinatra Prerequisite Test.

Tests Ruby runtime on the server with a minimal Sinatra application.
This helps verify Ruby prerequisites are working for Rails deployments.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 57: Ruby Prerequisite Test"
DESCRIPTION = """
Tests Ruby runtime prerequisites:
  - Ruby interpreter
  - Bundler gem management
  - Sinatra web framework
  - Basic HTTP routing
"""

APP_NAME = "demo57"
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
    print_header("Testing Ruby Prerequisites")

    show_app_structure(
        APP_NAME,
        [
            ("app.rb", "Sinatra application"),
            ("Gemfile", "Ruby dependencies"),
            ("config.ru", "Rack configuration"),
            ("hop3.toml", "Hop3 configuration"),
        ],
    )
    print_info("This demo verifies Ruby runtime prerequisites for Rails deployments.")
    pause(ctx.pause_between_steps)

    # Show hop3.toml
    show_file_content(APP_DIR / "hop3.toml", "hop3.toml:")
    pause(ctx.pause_between_steps)

    # Deploy the application
    print_header("Step 1: Deploy Application")
    deploy_app(ctx, APP_NAME, APP_DIR)
    set_hostname(ctx, APP_NAME, app_hostname)
    redeploy_app(ctx, APP_NAME, APP_DIR)
    wait_for_app(seconds=5, message="Waiting for Ruby app to start...")
    check_app_status(ctx, APP_NAME)

    # Test main endpoint
    print_header("Step 2: Test Application")
    test_app_via_curl(ctx, app_url, expected_content="Ruby")
    pause(ctx.pause_between_steps)

    # Test health check
    print_header("Step 3: Health Check")
    test_app_via_curl(ctx, f"{app_url}/up", expected_content="OK")
    print_success("Ruby prerequisites verified!")
    pause(ctx.pause_between_steps)

    # Cleanup
    cleanup_app(ctx, APP_NAME, app_url)
    print_success("Demo 57 completed: Ruby prerequisites test passed.")
