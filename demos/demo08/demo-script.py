# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 8: Python Poetry Project.

Demonstrates deploying a Python application using Poetry for dependency management.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 8: Python Poetry"
DESCRIPTION = """
Demonstrates Python deployment with Poetry:
  - pyproject.toml for modern Python packaging
  - poetry.lock for reproducible builds
  - Package-based project structure (src/app/)
"""

APP_NAME = "demo08"
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
    print_header("Deploying Python Poetry Project")

    show_app_structure(
        APP_NAME,
        [
            ("pyproject.toml", "Poetry configuration"),
            ("poetry.lock", "Locked dependencies"),
            ("src/app/", "Python package"),
            ("Procfile", "Gunicorn command"),
        ],
    )
    print_info("Poetry projects use pyproject.toml instead of requirements.txt.")
    print_blank()
    pause(ctx.pause_between_steps)

    # Show pyproject.toml
    show_file_content(APP_DIR / "pyproject.toml", "pyproject.toml:", max_lines=20)
    pause(ctx.pause_between_steps)

    # Show Procfile
    show_file_content(APP_DIR / "Procfile", "Procfile:")
    pause(ctx.pause_between_steps)

    # Deploy the application
    print_info("Hop3 will run 'poetry install' to set up dependencies.")
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
    test_app_via_curl(ctx, app_url, expected_content="Welcome to demo08")

    # Demo app management
    print_header("Application Management")

    list_apps(ctx)
    restart_app(ctx, APP_NAME, wait_seconds=2)

    # Cleanup
    cleanup_app(ctx, APP_NAME, app_url)
