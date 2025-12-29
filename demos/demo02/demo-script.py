# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 2: Docker Deployment.

Demonstrates deploying a Docker-based application with Hop3.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 2: Docker Deployment"
DESCRIPTION = """
Demonstrates deploying a Docker-based application with Hop3:
  - Building Docker images from Dockerfile
  - Deploying containers with Docker Compose
  - Routing traffic through nginx proxy
"""

APP_NAME = "demo02"
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
    from lib.server import ensure_docker

    app_hostname = ctx.get_app_hostname(APP_NAME)
    app_url = f"https://{app_hostname}"

    # Ensure Docker is available
    ensure_docker(ctx)
    pause(ctx.pause_between_steps)

    # Show app structure
    print_header("Deploying Docker Application")

    show_app_structure(
        APP_NAME,
        [
            ("app.py", "Flask application"),
            ("requirements.txt", "Python dependencies"),
            ("Dockerfile", "Container image definition"),
            ("hop3.toml", "Hop3 configuration (builder=docker)"),
        ],
    )
    print_info("Note: Hop3 generates docker-compose.yml automatically from the Dockerfile.")
    print_blank()
    pause(ctx.pause_between_steps)

    # Show Dockerfile
    show_file_content(APP_DIR / "Dockerfile", "Dockerfile:")
    pause(ctx.pause_between_steps)

    # Show hop3.toml
    show_file_content(APP_DIR / "hop3.toml", "Hop3 configuration (hop3.toml):")
    pause(ctx.pause_between_steps)

    # Deploy the application
    print_info("This will: 1) Build Docker image, 2) Generate compose file, 3) Start container")
    deploy_app(ctx, APP_NAME, APP_DIR)

    # Set hostname
    set_hostname(ctx, APP_NAME, app_hostname)

    # Redeploy to apply hostname
    redeploy_app(ctx, APP_NAME, APP_DIR)

    # Wait for container to start (Docker containers may take longer)
    wait_for_app(seconds=5, message="Waiting for container to start...")

    # Verify deployment
    check_app_status(ctx, APP_NAME)

    # Test application
    print_header("Testing Application")

    test_app_via_hop3(ctx, APP_NAME, app_url)
    test_app_via_curl(ctx, app_url, expected_content="Welcome to demo02")

    # Demo app management
    print_header("Application Management")

    list_apps(ctx)
    check_app_status(ctx, APP_NAME)
    restart_app(ctx, APP_NAME, wait_seconds=3)

    # Cleanup
    cleanup_app(ctx, APP_NAME, app_url)
