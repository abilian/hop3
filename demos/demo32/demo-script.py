# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 32: Native Python + Redis Addon.

Demonstrates deploying a native Python application with Redis addon.
This is the native equivalent of demo16 (Docker + Redis).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 32: Native Python + Redis"
DESCRIPTION = """
Demonstrates native Python deployment with Redis addon:
  - Building and deploying a native Python application
  - Creating a Redis instance via addon
  - Connecting the app to Redis
  - Testing counter and caching operations
"""

APP_NAME = "demo32"
APP_DIR = Path(__file__).parent / "app"
REDIS_NAME = "demo32-cache"


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
        print_warning,
        redeploy_app,
        set_hostname,
        show_app_structure,
        show_file_content,
        test_app_via_curl,
        wait_for_app,
    )
    from lib.commands import run_hop3
    from lib.server import ensure_redis

    app_hostname = ctx.hostname
    app_url = f"https://{app_hostname}"

    # Ensure Redis is available
    ensure_redis(ctx)
    pause(ctx.pause_between_steps)

    # Clean up any leftover Redis addon from previous failed runs
    run_hop3(f"addons:destroy {REDIS_NAME} --service-type redis", check=False, show=False)

    # Show app structure
    print_header("Deploying Native Python + Redis Application")

    show_app_structure(
        APP_NAME,
        [
            ("app.py", "Flask application with Redis support"),
            ("requirements.txt", "Python dependencies (flask, redis)"),
            ("hop3.toml", "Hop3 configuration (native Python builder)"),
        ],
    )
    print_info("This demo shows a native Python app connecting to a Redis addon.")
    print_info("Unlike demo16, this does NOT use Docker.")
    print_blank()
    pause(ctx.pause_between_steps)

    # Show hop3.toml
    show_file_content(APP_DIR / "hop3.toml", "hop3.toml:")
    pause(ctx.pause_between_steps)

    # Deploy the application
    print_header("Step 1: Deploy Native Python Application")
    deploy_app(ctx, APP_NAME, APP_DIR)
    set_hostname(ctx, APP_NAME, app_hostname)
    redeploy_app(ctx, APP_NAME, APP_DIR)
    wait_for_app(seconds=5, message="Waiting for application to start...")
    check_app_status(ctx, APP_NAME)

    # Test main endpoint
    print_header("Step 2: Test Application (Without Redis)")
    test_app_via_curl(ctx, app_url, expected_content="Welcome to demo32")
    pause(ctx.pause_between_steps)

    # Test Redis status - should show not_configured
    print_header("Step 3: Check Redis Status (Before Addon)")
    print_step("Testing /redis-status endpoint...")
    test_app_via_curl(ctx, f"{app_url}/redis-status", expected_content="not_configured")
    pause(ctx.pause_between_steps)

    # Create Redis addon
    print_header("Step 4: Create Redis Instance")
    print_step(f"Creating Redis instance '{REDIS_NAME}'...")
    result = run_hop3(f"addons:create redis {REDIS_NAME}", check=False)

    redis_available = result.returncode == 0
    if not redis_available:
        print_warning("Redis creation failed.")
        if result.stderr:
            print_info(f"  Error: {result.stderr.strip()}")
    else:
        print_success(f"Redis instance '{REDIS_NAME}' created.")
    pause(ctx.pause_between_steps)

    # Attach Redis to app
    if redis_available:
        print_header("Step 5: Attach Redis to Application")
        print_step(f"Attaching '{REDIS_NAME}' to '{APP_NAME}'...")
        result = run_hop3(
            f"addons:attach {REDIS_NAME} --app {APP_NAME} --service-type redis",
            check=False,
        )

        if result.returncode != 0:
            print_warning("Failed to attach Redis.")
            redis_available = False
        else:
            print_success("Redis attached. REDIS_URL is now set.")
        pause(ctx.pause_between_steps)

    # Redeploy to pick up REDIS_URL
    if redis_available:
        print_header("Step 6: Redeploy to Apply Configuration")
        print_step("Redeploying application with REDIS_URL...")
        redeploy_app(ctx, APP_NAME, APP_DIR)
        wait_for_app(seconds=5)

        # Test Redis connection
        print_header("Step 7: Verify Redis Connection")
        print_step("Testing /redis-status endpoint...")
        test_app_via_curl(ctx, f"{app_url}/redis-status", expected_content="connected")
        print_success("Native Python app connected to Redis!")
        pause(ctx.pause_between_steps)

        # Test counter operations
        print_header("Step 8: Test Counter Operations")
        print_step("Incrementing counter...")

        for i in range(3):
            curl_cmd = f"curl -sk {app_url}/counter/increment"
            result = subprocess.run(
                curl_cmd, shell=True, capture_output=True, text=True, check=False
            )
            if result.returncode == 0:
                print_info(f"  Increment {i + 1}: {result.stdout.strip()}")

        print_step("Getting counter value...")
        test_app_via_curl(ctx, f"{app_url}/counter", expected_content='"counter":3')
        print_success("Counter operations working!")
        pause(ctx.pause_between_steps)

        # Test cache operations
        print_header("Step 9: Test Cache Operations")
        print_step("Setting cache value...")
        test_app_via_curl(
            ctx, f"{app_url}/cache/set/greeting/hello-native", expected_content='"action":"set"'
        )

        print_step("Getting cache value...")
        test_app_via_curl(
            ctx, f"{app_url}/cache/get/greeting", expected_content="hello-native"
        )
        print_success("Cache operations working!")
        pause(ctx.pause_between_steps)

        # Cleanup Redis
        print_header("Step 10: Cleanup Redis")
        print_step("Detaching and destroying Redis...")
        run_hop3(
            f"addons:detach {REDIS_NAME} --app {APP_NAME} --service-type redis",
            check=False,
        )
        run_hop3(f"addons:destroy {REDIS_NAME} --service-type redis", check=False)
        print_success("Redis cleaned up.")
        pause(ctx.pause_between_steps)
    else:
        print_header("Redis Addon Commands")
        print_info("When Redis is available:")
        print_info(f"  hop3 addons:create redis {REDIS_NAME}")
        print_info(f"  hop3 addons:attach {REDIS_NAME} --app {APP_NAME} --service-type redis")
        print_blank()
        pause(ctx.pause_between_steps)

    # Cleanup app
    cleanup_app(ctx, APP_NAME, app_url)

    if redis_available:
        print_success("Demo 32 completed: Native Python + Redis workflow demonstrated.")
    else:
        print_success("Demo 32 completed: Native Python app deployed (Redis unavailable).")
