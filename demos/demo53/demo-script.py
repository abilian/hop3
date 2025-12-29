# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 53: PHP JSON API Application.

Demonstrates deploying a PHP application with JSON API endpoints.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 53: PHP JSON API"
DESCRIPTION = """
Demonstrates PHP deployment with Hop3:
  - PHP application with Apache
  - JSON API endpoints
  - Calculator and Fibonacci endpoints
"""

APP_NAME = "demo53"
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
    from lib.server import ensure_docker

    app_hostname = ctx.get_app_hostname(APP_NAME)
    app_url = f"https://{app_hostname}"

    # Ensure Docker is available
    ensure_docker(ctx)
    pause(ctx.pause_between_steps)

    # Show app structure
    print_header("Deploying PHP JSON API Application")

    show_app_structure(
        APP_NAME,
        [
            ("index.php", "PHP application"),
            ("Dockerfile", "Container image definition"),
            ("hop3.toml", "Hop3 configuration"),
        ],
    )
    print_info("PHP app with JSON API endpoints running on Apache.")
    print_blank()
    pause(ctx.pause_between_steps)

    # Show Dockerfile
    show_file_content(APP_DIR / "Dockerfile", "Dockerfile:")
    pause(ctx.pause_between_steps)

    # Show index.php
    show_file_content(APP_DIR / "index.php", "Application code (index.php):", max_lines=50)
    pause(ctx.pause_between_steps)

    # Deploy the application
    print_header("Step 1: Deploy Application")
    print_info("Building Docker image...")
    deploy_app(ctx, APP_NAME, APP_DIR)
    set_hostname(ctx, APP_NAME, app_hostname)
    redeploy_app(ctx, APP_NAME, APP_DIR)
    wait_for_app(seconds=5, message="Waiting for container to start...")
    check_app_status(ctx, APP_NAME)

    # Test main endpoint
    print_header("Step 2: Test Application")
    test_app_via_curl(ctx, app_url, expected_content="demo53")
    pause(ctx.pause_between_steps)

    # Test info endpoint
    print_header("Step 3: PHP Runtime Info")
    print_step("Testing /info endpoint...")
    test_app_via_curl(ctx, f"{app_url}/info", expected_content="php_version")
    print_success("PHP runtime information available!")
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
    print_success("Demo 53 completed: PHP JSON API deployment demonstrated.")
