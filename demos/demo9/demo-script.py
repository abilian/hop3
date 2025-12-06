# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 9: Minimal Go Application.

Demonstrates deploying a minimal Go HTTP server without external frameworks.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 9: Minimal Go"
DESCRIPTION = """
Demonstrates deploying a minimal Go application:
  - Standard library net/http only
  - No external dependencies
  - Single-file Go application
"""

APP_NAME = "golang-minimal"
APP_DIR = Path(__file__).parent / "golang-minimal"
DEFAULT_HOSTNAME = "a9.hop.demo"


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
    print_header("Deploying Minimal Go Application")

    show_app_structure(
        APP_NAME,
        [
            ("server.go", "Go HTTP server (stdlib only)"),
            ("Procfile", "Process definition"),
        ],
    )
    print_info("This is the simplest possible Go web server - no frameworks, no dependencies.")
    print_blank()
    pause(ctx.pause_between_steps)

    # Show server.go
    show_file_content(APP_DIR / "server.go", "server.go (minimal Go HTTP server):")
    pause(ctx.pause_between_steps)

    # Show Procfile
    show_file_content(APP_DIR / "Procfile", "Procfile:")
    pause(ctx.pause_between_steps)

    # Deploy the application
    deploy_app(ctx, APP_NAME, APP_DIR)

    # Set hostname
    set_hostname(ctx, APP_NAME, app_hostname)

    # Redeploy to apply hostname
    redeploy_app(ctx, APP_NAME, APP_DIR)

    # Wait for app
    wait_for_app(seconds=2)

    # Check status
    check_app_status(ctx, APP_NAME)

    # Test application
    print_header("Testing Application")

    test_app_via_hop3(ctx, APP_NAME, app_url)
    test_app_via_curl(ctx, app_url, expected_content="Hello world")

    # Demo app management
    print_header("Application Management")

    list_apps(ctx)
    restart_app(ctx, APP_NAME, wait_seconds=2)

    # Cleanup
    cleanup_app(ctx, APP_NAME, app_url)
