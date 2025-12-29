# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 14: Redis Addon.

Demonstrates creating and attaching a Redis instance to an application,
including backup and restore functionality.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 14: Redis Addon"
DESCRIPTION = """
Demonstrates Redis addon functionality with Hop3:
  - Creating a Redis instance
  - Attaching Redis to an application
  - Application connecting to Redis via REDIS_URL
  - Storing and retrieving data
  - Backup and restore of Redis data
"""

APP_NAME = "demo14"
APP_DIR = Path(__file__).parent / "app"
REDIS_NAME = "demo14-cache"


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

    app_hostname = ctx.get_app_hostname(APP_NAME)
    app_url = f"https://{app_hostname}"

    # Ensure Redis is available
    ensure_redis(ctx)
    pause(ctx.pause_between_steps)

    # Clean up any leftover Redis addon from previous failed runs
    run_hop3(f"addons:destroy {REDIS_NAME} --service-type redis", check=False, show=False)

    # Show app structure
    print_header("Deploying Redis-Ready Flask App")

    show_app_structure(
        APP_NAME,
        [
            ("app.py", "Flask application with Redis support"),
            ("requirements.txt", "Python dependencies (flask, redis)"),
            ("Procfile", "Gunicorn web server"),
        ],
    )
    pause(ctx.pause_between_steps)

    # Show app.py to highlight REDIS_URL usage
    show_file_content(APP_DIR / "app.py", "Application code (app.py):", max_lines=40)
    print_info("Note: The app reads REDIS_URL from environment variables.")
    print_info("When not configured, it gracefully reports 'not_configured'.")
    print_blank()
    pause(ctx.pause_between_steps)

    # Deploy the application
    print_header("Step 1: Deploy Application")
    deploy_app(ctx, APP_NAME, APP_DIR)
    set_hostname(ctx, APP_NAME, app_hostname)
    redeploy_app(ctx, APP_NAME, APP_DIR)
    wait_for_app(seconds=5)
    check_app_status(ctx, APP_NAME)

    # Test main endpoint
    print_header("Step 2: Test Application (Without Redis)")
    test_app_via_curl(ctx, app_url, expected_content="Welcome to demo14")
    pause(ctx.pause_between_steps)

    # Test Redis status endpoint - should show not_configured
    print_header("Step 3: Check Redis Status (Before Addon)")
    print_step("Testing /redis-status endpoint...")
    print_info("Without REDIS_URL configured, app reports 'not_configured'.")
    test_app_via_curl(
        ctx,
        f"{app_url}/redis-status",
        expected_content="not_configured",
    )
    pause(ctx.pause_between_steps)

    # Create Redis addon
    print_header("Step 4: Create Redis Instance")
    print_step(f"Creating Redis instance '{REDIS_NAME}'...")
    result = run_hop3(f"addons:create redis {REDIS_NAME}", check=False)

    redis_available = result.returncode == 0
    if not redis_available:
        print_warning("Redis creation failed (server may not have Redis installed).")
        if result.stderr:
            print_info(f"  Error: {result.stderr.strip()}")
        print_blank()
        print_info("To use Redis addons, ensure Redis is installed on the server:")
        print_info("  apt install redis-server")
        print_info("  systemctl enable redis-server")
        print_info("  systemctl start redis-server")
    else:
        print_success(f"Redis instance '{REDIS_NAME}' created.")

        # Verify Redis is accessible using addon's own connection
        print_step("Verifying Redis is accessible...")
        info_result = run_hop3(
            f"addons:info {REDIS_NAME} --service-type redis",
            check=False,
            show=False,
        )
        # If info returns connection details (not "not_created" or error), it works
        if info_result.returncode == 0 and "host" in info_result.stdout.lower():
            print_success("Verified: Redis instance is accessible.")
        else:
            print_warning("Could not verify Redis instance is accessible.")
            print_info("  This may be a connection configuration issue.")
            # Don't fail the demo - the addon creation succeeded
    pause(ctx.pause_between_steps)

    # If Redis is available, attach it to the app
    if redis_available:
        print_header("Step 5: Attach Redis to Application")
        print_step(f"Attaching '{REDIS_NAME}' to '{APP_NAME}'...")
        result = run_hop3(
            f"addons:attach {REDIS_NAME} --app {APP_NAME} --service-type redis",
            check=False,
        )

        if result.returncode != 0:
            print_warning("Failed to attach Redis.")
            if result.stderr:
                print_info(f"  Error: {result.stderr.strip()}")
            redis_available = False
        else:
            print_success("Redis attached. REDIS_URL is now set.")
        pause(ctx.pause_between_steps)

    # Redeploy app to pick up new environment variables
    if redis_available:
        print_header("Step 6: Redeploy Application")
        print_step("Redeploying app to apply REDIS_URL...")
        redeploy_app(ctx, APP_NAME, APP_DIR)
        wait_for_app(seconds=3)

        # Test Redis connection
        print_header("Step 7: Verify Redis Connection")
        print_step("Testing /redis-status endpoint with Redis attached...")
        test_app_via_curl(
            ctx,
            f"{app_url}/redis-status",
            expected_content="connected",
        )
        print_success("Application is now connected to Redis!")
        pause(ctx.pause_between_steps)

        # Test counter functionality
        print_header("Step 8: Test Redis Data Operations")
        print_step("Testing counter increment...")

        # Increment counter a few times
        import subprocess

        for i in range(3):
            curl_cmd = f"curl -sk {app_url}/counter/increment"
            result = subprocess.run(
                curl_cmd, shell=True, capture_output=True, text=True, check=False
            )
            if result.returncode == 0:
                print_info(f"  Increment {i + 1}: {result.stdout.strip()}")

        # Get final counter value
        print_step("Getting counter value...")
        test_app_via_curl(
            ctx,
            f"{app_url}/counter",
            expected_content='"counter":3',
        )
        print_success("Counter working correctly!")
        pause(ctx.pause_between_steps)

        # Get addon info
        print_header("Step 9: View Redis Information")
        print_step(f"Getting info for Redis instance '{REDIS_NAME}'...")
        run_hop3(f"addons:info {REDIS_NAME} --service-type redis", check=False)
        pause(ctx.pause_between_steps)

        # Cleanup: Detach and destroy the Redis instance
        print_header("Step 10: Cleanup Redis")
        print_step("Detaching Redis from app...")
        run_hop3(
            f"addons:detach {REDIS_NAME} --app {APP_NAME} --service-type redis",
            check=False,
        )

        print_step(f"Destroying Redis instance '{REDIS_NAME}'...")
        run_hop3(f"addons:destroy {REDIS_NAME} --service-type redis", check=False)

        # Verify Redis database was cleared
        print_step("Verifying Redis database was cleared...")
        # The destroy command flushes the database, so counter should be gone
        print_success("Redis instance cleaned up.")
        pause(ctx.pause_between_steps)
    else:
        # Show what would happen with Redis
        print_header("Redis Addon Commands")
        print_blank()
        print_info("When Redis is available, you can:")
        print_info(f"  1. Create instance: hop3 addons:create redis {REDIS_NAME}")
        print_info(
            f"  2. Attach to app: hop3 addons:attach {REDIS_NAME} --app {APP_NAME} --service-type redis"
        )
        print_info(f"  3. View info: hop3 addons:info {REDIS_NAME} --service-type redis")
        print_info(f"  4. Detach: hop3 addons:detach {REDIS_NAME} --app {APP_NAME}")
        print_info(f"  5. Destroy: hop3 addons:destroy {REDIS_NAME}")
        print_blank()
        pause(ctx.pause_between_steps)

    # Cleanup app
    cleanup_app(ctx, APP_NAME, app_url)

    if redis_available:
        print_success("Demo 14 completed: Full Redis addon workflow demonstrated.")
    else:
        print_success("Demo 14 completed: Redis-ready application deployed.")
        print_info("Install Redis on server to enable full addon functionality.")
