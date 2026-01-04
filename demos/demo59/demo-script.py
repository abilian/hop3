# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 59: Elixir/Plug Prerequisite Test.

Tests Elixir runtime on the server with a minimal Plug application.
This helps verify Elixir prerequisites for Phoenix deployments.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 59: Elixir Prerequisite Test"
DESCRIPTION = """
Tests Elixir runtime prerequisites:
  - Elixir interpreter
  - Mix build tool
  - Plug web framework
  - Cowboy HTTP server
"""

APP_NAME = "demo59"
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
    print_header("Testing Elixir Prerequisites")

    show_app_structure(
        APP_NAME,
        [
            ("lib/demo59.ex", "Plug application"),
            ("mix.exs", "Elixir dependencies"),
            ("hop3.toml", "Hop3 configuration"),
        ],
    )
    print_info("This demo verifies Elixir runtime prerequisites for Phoenix deployments.")
    pause(ctx.pause_between_steps)

    # Show hop3.toml
    show_file_content(APP_DIR / "hop3.toml", "hop3.toml:")
    pause(ctx.pause_between_steps)

    # Deploy the application
    print_header("Step 1: Deploy Application")
    deploy_app(ctx, APP_NAME, APP_DIR)
    set_hostname(ctx, APP_NAME, app_hostname)
    redeploy_app(ctx, APP_NAME, APP_DIR)
    wait_for_app(seconds=10, message="Waiting for Elixir app to start...")
    check_app_status(ctx, APP_NAME)

    # Test main endpoint
    print_header("Step 2: Test Application")
    test_app_via_curl(ctx, app_url, expected_content="Elixir")
    pause(ctx.pause_between_steps)

    # Test health check
    print_header("Step 3: Health Check")
    test_app_via_curl(ctx, f"{app_url}/up", expected_content="OK")
    print_success("Elixir prerequisites verified!")
    pause(ctx.pause_between_steps)

    # Cleanup
    cleanup_app(ctx, APP_NAME, app_url)
    print_success("Demo 59 completed: Elixir prerequisites test passed.")
