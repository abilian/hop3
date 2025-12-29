# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 50: Native Node.js/Express Application.

Demonstrates deploying a Node.js/Express application natively without Docker.
This is the native builder equivalent of demo18.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 50: Native Node.js"
DESCRIPTION = """
Demonstrates native Node.js deployment with Hop3:
  - Node.js application without Docker
  - Express.js web framework
  - JSON API endpoints
  - Automatic npm install during deployment
"""

APP_NAME = "demo50"
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
    print_header("Deploying Native Node.js Application")

    show_app_structure(
        APP_NAME,
        [
            ("app.js", "Express.js application"),
            ("package.json", "Node.js dependencies"),
            ("Procfile", "Process definition"),
            ("hop3.toml", "Hop3 configuration"),
        ],
    )
    print_info("Node.js apps are detected by package.json - no Docker required!")
    print_blank()
    pause(ctx.pause_between_steps)

    # Show Procfile
    show_file_content(APP_DIR / "Procfile", "Procfile:")
    pause(ctx.pause_between_steps)

    # Show app.js
    show_file_content(APP_DIR / "app.js", "Application code (app.js):", max_lines=40)
    pause(ctx.pause_between_steps)

    # Deploy the application
    print_header("Step 1: Deploy Application")
    print_info("Installing npm dependencies natively...")
    deploy_app(ctx, APP_NAME, APP_DIR)
    set_hostname(ctx, APP_NAME, app_hostname)
    redeploy_app(ctx, APP_NAME, APP_DIR)
    wait_for_app(seconds=3, message="Waiting for app to start...")
    check_app_status(ctx, APP_NAME)

    # Test main endpoint
    print_header("Step 2: Test Application")
    test_app_via_curl(ctx, app_url, expected_content="Native Node.js/Express")
    pause(ctx.pause_between_steps)

    # Test info endpoint
    print_header("Step 3: Node.js Runtime Info")
    print_step("Testing /info endpoint...")
    test_app_via_curl(ctx, f"{app_url}/info", expected_content="node_version")
    print_success("Node.js runtime information available!")
    pause(ctx.pause_between_steps)

    # Test stats endpoint
    print_header("Step 4: Application Stats")
    print_step("Testing /stats endpoint...")
    # JSON may be compact (no space after colon)
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

    # Test health check
    print_header("Step 6: Health Check")
    test_app_via_curl(ctx, f"{app_url}/health", expected_content='"status":"healthy"')
    print_success("Health check passes!")
    pause(ctx.pause_between_steps)

    # Cleanup
    cleanup_app(ctx, APP_NAME, app_url)
    print_success("Demo 50 completed: Native Node.js deployment demonstrated.")
