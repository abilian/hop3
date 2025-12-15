# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 5: Go with Gin Framework.

Demonstrates deploying a Go application using the Gin web framework.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 5: Go with Gin"
DESCRIPTION = """
Demonstrates deploying a Go application with Hop3:
  - Gin web framework for routing
  - go.mod for dependency management
  - Automatic Go module download
"""

APP_NAME = "demo05"
APP_DIR = Path(__file__).parent / "app"
DEFAULT_HOSTNAME = "demo05.hop"


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

    app_hostname = DEFAULT_HOSTNAME
    app_url = f"https://{app_hostname}"

    # Show app structure
    print_header("Deploying Go/Gin Application")

    show_app_structure(
        APP_NAME,
        [
            ("server.go", "Go application with Gin"),
            ("go.mod", "Go module definition"),
            ("go.sum", "Dependency checksums"),
            ("Procfile", "Process definition"),
        ],
    )
    print_info("Go apps are detected by go.mod file.")
    print_blank()
    pause(ctx.pause_between_steps)

    # Show server.go
    show_file_content(APP_DIR / "server.go", "server.go (Gin application):")
    pause(ctx.pause_between_steps)

    # Show go.mod
    show_file_content(APP_DIR / "go.mod", "go.mod:")
    pause(ctx.pause_between_steps)

    # Deploy the application
    print_info("Hop3 will download Go modules and build the application.")
    deploy_app(ctx, APP_NAME, APP_DIR)

    # Set hostname
    set_hostname(ctx, APP_NAME, app_hostname)

    # Redeploy to apply hostname
    redeploy_app(ctx, APP_NAME, APP_DIR)

    # Wait for app - Go apps need longer to compile on first deploy
    wait_for_app(seconds=10, message="Waiting for Go compilation and app startup...")

    # Check status
    check_app_status(ctx, APP_NAME)

    # Test application
    print_header("Testing Application")

    test_app_via_hop3(ctx, APP_NAME, app_url)
    # Go apps may take longer to start - use more retries
    test_app_via_curl(ctx, app_url, expected_content="Welcome to demo05", max_retries=15)

    # Demo app management
    print_header("Application Management")

    list_apps(ctx)
    restart_app(ctx, APP_NAME, wait_seconds=2)

    # Cleanup
    cleanup_app(ctx, APP_NAME, app_url)
