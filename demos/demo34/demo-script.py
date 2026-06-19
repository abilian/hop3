# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 34: Declarative MySQL Provider.

Demonstrates declaring an addon dependency in hop3.toml via the [[addons]]
section. Hop3 reads that declaration at deploy time, provisions the MySQL
database, injects DATABASE_URL, and wires the app to it automatically — no
manual ``addon create`` / ``addon attach`` commands needed.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 34: Declarative MySQL Provider"
DESCRIPTION = """
Demonstrates declarative addon provisioning via hop3.toml:
  - The app declares its MySQL dependency with an [[addons]] section
  - Hop3 provisions the database and sets DATABASE_URL automatically on deploy
  - No manual addon commands — the app is connected as soon as it is deployed
"""

APP_NAME = "demo34"
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
    print_header("Deploying App with Declarative MySQL Provider")
    show_app_structure(
        APP_NAME,
        [
            ("app.py", "Flask application with MySQL support"),
            ("requirements.txt", "Python dependencies (flask, PyMySQL)"),
            ("hop3.toml", "Hop3 configuration with an [[addons]] section"),
        ],
    )
    print_info("The app declares a MySQL dependency in hop3.toml via [[addons]].")
    print_info("Hop3 provisions the database and injects DATABASE_URL automatically")
    print_info("at deploy time — no 'addon create' / 'addon attach' needed.")
    print_blank()
    pause(ctx.pause_between_steps)

    # Show hop3.toml - emphasize the [[addons]] section
    print_header("hop3.toml with an [[addons]] Section")
    show_file_content(APP_DIR / "hop3.toml", "hop3.toml:")
    print_blank()
    print_info('Note the [[addons]] section: type = "mysql".')
    pause(ctx.pause_between_steps)

    # Deploy — the declared addon is auto-provisioned and DATABASE_URL is wired in.
    print_header("Step 1: Deploy (MySQL auto-provisioned)")
    deploy_app(ctx, APP_NAME, APP_DIR)
    set_hostname(ctx, APP_NAME, app_hostname)
    redeploy_app(ctx, APP_NAME, APP_DIR)
    wait_for_app(seconds=5, message="Waiting for application to start...")
    check_app_status(ctx, APP_NAME)

    # Test main endpoint
    print_header("Step 2: Test Application")
    test_app_via_curl(ctx, app_url, expected_content="Welcome to demo34")
    pause(ctx.pause_between_steps)

    # The [[addons]] declaration provisioned MySQL at deploy, so the app is
    # already connected — verify the auto-wired DATABASE_URL works.
    print_header("Step 3: Verify Auto-Provisioned Database")
    print_info("DATABASE_URL was set automatically from the [[addons]] declaration.")
    test_app_via_curl(ctx, f"{app_url}/db-status", expected_content="connected")
    test_app_via_curl(ctx, f"{app_url}/db-test", expected_content="success")
    print_success("App auto-connected to MySQL via [[addons]].")
    pause(ctx.pause_between_steps)

    # Cleanup — 'app destroy' cascades to the auto-provisioned addon (no leak).
    cleanup_app(ctx, APP_NAME, app_url)

    print_blank()
    print_header("Summary: Declarative [[addons]] Provisioning")
    print_info("Declaring an addon in hop3.toml:")
    print_info("  [[addons]]")
    print_info('  type = "mysql"')
    print_blank()
    print_info("...makes Hop3 provision the database, inject DATABASE_URL, and wire")
    print_info("the app to it automatically — no manual addon commands.")
    print_blank()
    print_success("Demo 34 completed: declarative MySQL auto-provisioning.")
