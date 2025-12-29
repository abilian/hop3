# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 52: Native Ruby/Sinatra Application.

Demonstrates deploying a Ruby/Sinatra application natively without Docker.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 52: Native Ruby/Sinatra"
DESCRIPTION = """
Demonstrates native Ruby deployment with Hop3:
  - Ruby application without Docker
  - Sinatra web framework
  - JSON API endpoints
  - Fibonacci performance demo
"""

APP_NAME = "demo52"
APP_DIR = Path(__file__).parent / "app"


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

    app_hostname = ctx.get_app_hostname(APP_NAME)
    app_url = f"https://{app_hostname}"

    # Show app structure
    print_header("Deploying Native Ruby/Sinatra Application")

    show_app_structure(
        APP_NAME,
        [
            ("app.rb", "Sinatra application"),
            ("Gemfile", "Ruby dependencies"),
            ("Procfile", "Process definition"),
            ("hop3.toml", "Hop3 configuration"),
        ],
    )
    print_info("Ruby apps are detected by Gemfile - no Docker required!")
    print_blank()
    pause(ctx.pause_between_steps)

    # Show Procfile
    show_file_content(APP_DIR / "Procfile", "Procfile:")
    pause(ctx.pause_between_steps)

    # Show app.rb
    show_file_content(APP_DIR / "app.rb", "Application code (app.rb):", max_lines=50)
    pause(ctx.pause_between_steps)

    # Deploy the application
    print_header("Step 1: Deploy Application")
    print_info("Installing Ruby gems natively...")
    deploy_app(ctx, APP_NAME, APP_DIR)
    set_hostname(ctx, APP_NAME, app_hostname)
    redeploy_app(ctx, APP_NAME, APP_DIR)
    wait_for_app(seconds=3, message="Waiting for app to start...")
    check_app_status(ctx, APP_NAME)

    # Test main endpoint
    print_header("Step 2: Test Application")
    test_app_via_curl(ctx, app_url, expected_content="Native Ruby/Sinatra")
    pause(ctx.pause_between_steps)

    # Test info endpoint
    print_header("Step 3: Ruby Runtime Info")
    print_step("Testing /info endpoint...")
    test_app_via_curl(ctx, f"{app_url}/info", expected_content="ruby_version")
    print_success("Ruby runtime information available!")
    pause(ctx.pause_between_steps)

    # Test stats endpoint
    print_header("Step 4: Application Stats")
    print_step("Testing /stats endpoint...")
    test_app_via_curl(ctx, f"{app_url}/stats", expected_content='"requests":1')
    test_app_via_curl(ctx, f"{app_url}/stats", expected_content='"requests":2')
    print_success("Request counter working!")
    pause(ctx.pause_between_steps)

    # Test calculator endpoint
    print_header("Step 5: API Functionality")
    print_step("Testing calculator API...")
    test_app_via_curl(
        ctx, f"{app_url}/calculate/add/10/5", expected_content='"result":15'
    )
    test_app_via_curl(
        ctx, f"{app_url}/calculate/multiply/3/7", expected_content='"result":21'
    )
    print_success("Calculator API working!")
    pause(ctx.pause_between_steps)

    # Test Fibonacci endpoint (performance)
    print_header("Step 6: Performance Demo")
    print_step("Testing Fibonacci calculation...")
    test_app_via_curl(ctx, f"{app_url}/fib/30", expected_content='"result":832040')
    print_success("Fibonacci calculation working!")
    pause(ctx.pause_between_steps)

    # Test health check
    print_header("Step 7: Health Check")
    test_app_via_curl(ctx, f"{app_url}/health", expected_content='"status":"healthy"')
    print_success("Health check passes!")
    pause(ctx.pause_between_steps)

    # Cleanup
    cleanup_app(ctx, APP_NAME, app_url)
    print_success("Demo 52 completed: Native Ruby/Sinatra deployment demonstrated.")
