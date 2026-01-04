# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 19: Docker Go/Gin Application.

Demonstrates deploying a Go application with Gin framework using Docker.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 19: Docker Go"
DESCRIPTION = """
Demonstrates Docker deployment with Go/Gin:
  - Go application in Docker container
  - Multi-stage build for smaller image
  - Gin web framework
  - High-performance JSON API
"""

APP_NAME = "demo19"
APP_DIR = Path(__file__).parent / "app"

# This demo requires Docker daemon for building/deploying containers
REQUIRES = ["docker"]


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
    print_header("Deploying Docker Go Application")

    show_app_structure(
        APP_NAME,
        [
            ("main.go", "Go application with Gin"),
            ("go.mod", "Go module definition"),
            ("Dockerfile", "Multi-stage build"),
            ("hop3.toml", "Hop3 configuration"),
        ],
    )
    print_info("This demo uses a multi-stage Docker build for a minimal image.")
    print_blank()
    pause(ctx.pause_between_steps)

    # Show Dockerfile
    show_file_content(APP_DIR / "Dockerfile", "Dockerfile (multi-stage build):")
    print_info("Stage 1: Build Go binary with full toolchain")
    print_info("Stage 2: Copy binary to minimal Alpine image")
    print_blank()
    pause(ctx.pause_between_steps)

    # Show main.go
    show_file_content(APP_DIR / "main.go", "Application code (main.go):", max_lines=50)
    pause(ctx.pause_between_steps)

    # Deploy the application
    print_header("Step 1: Deploy Application")
    print_info("Building Docker image (multi-stage)...")
    deploy_app(ctx, APP_NAME, APP_DIR)
    set_hostname(ctx, APP_NAME, app_hostname)
    redeploy_app(ctx, APP_NAME, APP_DIR)
    wait_for_app(seconds=5, message="Waiting for container to start...")
    check_app_status(ctx, APP_NAME)

    # Test main endpoint
    print_header("Step 2: Test Application")
    test_app_via_curl(ctx, app_url, expected_content="Docker Go/Gin")
    pause(ctx.pause_between_steps)

    # Test info endpoint
    print_header("Step 3: Go Runtime Info")
    print_step("Testing /info endpoint...")
    test_app_via_curl(ctx, f"{app_url}/info", expected_content="go_version")
    print_success("Go runtime information available!")
    pause(ctx.pause_between_steps)

    # Test stats endpoint
    print_header("Step 4: Application Stats")
    print_step("Testing /stats endpoint...")
    test_app_via_curl(ctx, f"{app_url}/stats", expected_content='"requests":1')
    test_app_via_curl(ctx, f"{app_url}/stats", expected_content='"requests":2')
    print_success("Request counter working!")
    pause(ctx.pause_between_steps)

    # Test calculator
    print_header("Step 5: Calculator API")
    print_step("Testing calculator...")
    test_app_via_curl(
        ctx, f"{app_url}/calculate/add/100/50", expected_content='"result":150'
    )
    test_app_via_curl(
        ctx, f"{app_url}/calculate/multiply/12/12", expected_content='"result":144'
    )
    print_success("Calculator API working!")
    pause(ctx.pause_between_steps)

    # Test Fibonacci (showcase Go performance)
    print_header("Step 6: Performance Test (Fibonacci)")
    print_step("Computing Fibonacci numbers...")
    test_app_via_curl(ctx, f"{app_url}/fib/10", expected_content='"result":55')
    test_app_via_curl(ctx, f"{app_url}/fib/30", expected_content='"result":832040')
    print_success("Fibonacci computation fast!")
    pause(ctx.pause_between_steps)

    # Test health check
    print_header("Step 7: Health Check")
    test_app_via_curl(ctx, f"{app_url}/health", expected_content='"status":"healthy"')
    print_success("Health check passes!")
    pause(ctx.pause_between_steps)

    # Cleanup
    cleanup_app(ctx, APP_NAME, app_url)
    print_success("Demo 19 completed: Docker Go deployment demonstrated.")
