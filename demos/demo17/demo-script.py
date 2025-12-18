# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 17: Docker Multi-Container Application.

Demonstrates deploying a multi-container application using custom docker-compose.yml.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 17: Docker Multi-Container"
DESCRIPTION = """
Demonstrates multi-container Docker deployment:
  - Custom docker-compose.yml with multiple services
  - Web app + Redis running together
  - Docker networking between containers
  - Volume persistence for data
"""

APP_NAME = "demo17"
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

    app_hostname = ctx.hostname
    app_url = f"https://{app_hostname}"

    # Ensure Docker is available
    ensure_docker(ctx)
    pause(ctx.pause_between_steps)

    # Show app structure
    print_header("Deploying Multi-Container Docker Application")

    show_app_structure(
        APP_NAME,
        [
            ("app.py", "Flask application"),
            ("requirements.txt", "Python dependencies"),
            ("Dockerfile", "Web service container"),
            ("docker-compose.yml", "Multi-container orchestration"),
            ("hop3.toml", "Hop3 configuration"),
        ],
    )
    print_info("This demo uses a custom docker-compose.yml with web + Redis services.")
    print_blank()
    pause(ctx.pause_between_steps)

    # Show docker-compose.yml
    print_header("Docker Compose Configuration")
    show_file_content(APP_DIR / "docker-compose.yml", "docker-compose.yml:")
    print_info("Key features:")
    print_info("  - 'web' service: Flask app exposed to Hop3 proxy")
    print_info("  - 'redis' service: Internal Redis for caching/state")
    print_info("  - 'redis_data' volume: Persistent storage")
    print_blank()
    pause(ctx.pause_between_steps)

    # Deploy the application
    print_header("Step 1: Deploy Multi-Container Application")
    print_info("Hop3 detects docker-compose.yml and uses it for deployment.")
    deploy_app(ctx, APP_NAME, APP_DIR)
    set_hostname(ctx, APP_NAME, app_hostname)
    redeploy_app(ctx, APP_NAME, APP_DIR)
    wait_for_app(seconds=8, message="Waiting for containers to start...")
    check_app_status(ctx, APP_NAME)

    # Test main endpoint
    print_header("Step 2: Test Application")
    test_app_via_curl(ctx, app_url, expected_content="Multi-container Docker app")
    pause(ctx.pause_between_steps)

    # Test Redis connection (internal networking)
    print_header("Step 3: Verify Redis Connection")
    print_step("Testing /redis-status endpoint...")
    print_info("The web container connects to Redis via Docker networking.")
    test_app_via_curl(ctx, f"{app_url}/redis-status", expected_content="connected")
    print_success("Web container can reach Redis container!")
    pause(ctx.pause_between_steps)

    # Test visit counter (demonstrates shared state)
    print_header("Step 4: Test Shared State (Visit Counter)")
    # Reset counter to ensure deterministic test
    print_step("Resetting visit counter...")
    from lib.commands import run_local
    run_local(f"curl -sk {app_url}/visits/reset", show=False, check=False)

    print_step("Visiting /visits multiple times...")
    for i in range(3):
        # JSON may be compact (no space after colon)
        test_app_via_curl(
            ctx, f"{app_url}/visits", expected_content=f'"visits":{i + 1}'
        )
    print_success("Visit counter increments correctly (state in Redis)!")
    pause(ctx.pause_between_steps)

    # Test data storage
    print_header("Step 5: Test Data Storage")
    print_step("Storing data: greeting = hello-world")
    test_app_via_curl(
        ctx, f"{app_url}/data/greeting/hello-world", expected_content='"action":"set"'
    )

    print_step("Retrieving data...")
    test_app_via_curl(ctx, f"{app_url}/data/greeting", expected_content="hello-world")
    print_success("Data storage working!")
    pause(ctx.pause_between_steps)

    # Test health check
    print_header("Step 6: Health Check")
    print_step("Testing /health endpoint...")
    test_app_via_curl(ctx, f"{app_url}/health", expected_content='"status":"healthy"')
    print_success("Health check passes (both services healthy)!")
    pause(ctx.pause_between_steps)

    # Cleanup
    cleanup_app(ctx, APP_NAME, app_url)
    print_success("Demo 17 completed: Multi-container Docker deployment demonstrated.")
