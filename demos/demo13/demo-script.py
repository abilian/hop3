# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 13: Build Hooks.

Demonstrates pre-build, post-build, and pre-run hooks using hop3.toml.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 13: Build Hooks"
DESCRIPTION = """
Demonstrates build lifecycle hooks with hop3.toml:
  - before-build: Runs before dependency installation
  - build: Runs after dependencies are installed
  - before-run: Runs before the application starts
"""

APP_NAME = "demo13"
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
    print_header("Deploying App with Build Hooks")

    show_app_structure(
        APP_NAME,
        [
            ("app.py", "Flask application"),
            ("requirements.txt", "Python dependencies"),
            ("hop3.toml", "Hop3 configuration with hooks"),
            ("scripts/pre_build.py", "Pre-build hook script"),
            ("scripts/post_build.py", "Post-build hook script"),
            ("scripts/pre_run.py", "Pre-run hook script"),
        ],
    )
    pause(ctx.pause_between_steps)

    # Show hop3.toml configuration
    print_header("Step 1: Review hop3.toml Configuration")
    show_file_content(APP_DIR / "hop3.toml", "hop3.toml (build hooks configuration):")
    print_blank()
    print_info("Build lifecycle hooks:")
    print_info("  1. before-build: Runs BEFORE pip install")
    print_info("  2. build: Runs AFTER pip install (asset compilation)")
    print_info("  3. before-run: Runs BEFORE app starts (migrations)")
    print_blank()
    pause(ctx.pause_between_steps)

    # Show pre-build script
    print_header("Step 2: Review Pre-build Script")
    show_file_content(
        APP_DIR / "scripts" / "pre_build.py",
        "scripts/pre_build.py:",
        max_lines=20
    )
    print_info("This script runs before dependencies are installed.")
    print_info("Use for: validation, downloading assets, environment checks.")
    pause(ctx.pause_between_steps)

    # Show post-build script
    print_header("Step 3: Review Post-build Script")
    show_file_content(
        APP_DIR / "scripts" / "post_build.py",
        "scripts/post_build.py:",
        max_lines=20
    )
    print_info("This script runs after dependencies are installed.")
    print_info("Use for: asset compilation, generating static files.")
    pause(ctx.pause_between_steps)

    # Deploy the application
    print_header("Step 4: Deploy Application (Watch for Hook Output)")
    print_info("During deployment, you should see output from each hook:")
    print_info("  - 'PRE-BUILD HOOK: Starting...'")
    print_info("  - 'POST-BUILD HOOK: Starting...'")
    print_info("  - 'PRE-RUN HOOK: Starting...'")
    print_blank()
    pause(ctx.pause_between_steps)

    deploy_app(ctx, APP_NAME, APP_DIR)
    set_hostname(ctx, APP_NAME, app_hostname)
    redeploy_app(ctx, APP_NAME, APP_DIR)
    wait_for_app(seconds=3)

    # Check app status
    check_app_status(ctx, APP_NAME)

    # Test the application
    print_header("Step 5: Test Application")
    test_app_via_curl(ctx, app_url, expected_content="Welcome to demo13")
    pause(ctx.pause_between_steps)

    # Check build info created by hooks
    print_header("Step 6: Verify Hook Results")
    print_step("Checking /build-info endpoint (shows files created by hooks)...")
    test_app_via_curl(
        ctx, f"{app_url}/build-info",
        expected_content="build_info_exists",
    )
    print_blank()
    print_info("The /build-info endpoint shows:")
    print_info("  - build_info.txt: Created by pre-build hook")
    print_info("  - app.min.css: Created by post-build hook")
    pause(ctx.pause_between_steps)

    # Demonstrate common use cases
    print_header("Common Use Cases for Hooks")
    print_blank()
    print_info("before-build (prebuild):")
    print_info("  - Install system dependencies")
    print_info("  - Run linters or type checkers")
    print_info("  - Download external assets")
    print_blank()
    print_info("build (postbuild):")
    print_info("  - Compile CSS/JS (Sass, TypeScript, Webpack)")
    print_info("  - Generate static files (Django collectstatic)")
    print_info("  - Run test suite")
    print_blank()
    print_info("before-run (prerun):")
    print_info("  - Run database migrations")
    print_info("  - Warm up caches")
    print_info("  - Validate environment variables")
    pause(ctx.pause_between_steps)

    # Cleanup
    cleanup_app(ctx, APP_NAME, app_url)

    print_success("Demo 13 completed: Build hooks demonstrated.")
