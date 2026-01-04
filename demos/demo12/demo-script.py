# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo 12: Backup and Restore.

Demonstrates backing up and restoring application data.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

# Demo metadata
TITLE = "Demo 12: Backup and Restore"
DESCRIPTION = """
Demonstrates backup and restore functionality with Hop3:
  - Creating application data
  - Creating application backups
  - Destroying data and restoring from backup
  - Verifying restored data
"""

APP_NAME = "demo12"
APP_DIR = Path(__file__).parent / "app"


def run(ctx: DemoContext) -> None:
    """Run the demo."""
    from lib import (
        check_app_status,
        cleanup_app,
        curl_request,
        deploy_app,
        pause,
        print_blank,
        print_error,
        print_header,
        print_info,
        print_step,
        print_success,
        print_warning,
        redeploy_app,
        restart_app,
        set_hostname,
        show_app_structure,
        test_app_via_curl,
        wait_for_app,
    )
    from lib.commands import run_hop3

    app_hostname = ctx.get_app_hostname(APP_NAME)
    app_url = f"https://{app_hostname}"

    # Show app structure
    print_header("Deploying App with Persistent Data")

    show_app_structure(
        APP_NAME,
        [
            ("app.py", "Flask application with data storage"),
            ("requirements.txt", "Python dependencies"),
            ("Procfile", "Gunicorn web server"),
        ],
    )
    print_info("This app stores notes in a JSON file that can be backed up.")
    print_blank()
    pause(ctx.pause_between_steps)

    # Deploy the application
    print_header("Step 1: Deploy Application")
    deploy_app(ctx, APP_NAME, APP_DIR)
    set_hostname(ctx, APP_NAME, app_hostname)
    redeploy_app(ctx, APP_NAME, APP_DIR)
    wait_for_app(seconds=5)
    check_app_status(ctx, APP_NAME)

    # Test basic endpoint
    test_app_via_curl(ctx, app_url, expected_content="Welcome to demo12")
    pause(ctx.pause_between_steps)

    # Create some data
    print_header("Step 2: Create Application Data")
    print_step("Adding notes to the application...")

    # Add a few notes
    notes_to_add = ["First important note", "Second note for backup", "Third test note"]
    for note in notes_to_add:
        note_encoded = note.replace(" ", "%20")
        result = curl_request(ctx, f"{app_url}/notes/add/{note_encoded}")
        if result.returncode == 0:
            print_info(f"  Added: {note}")

    pause(ctx.pause_between_steps)

    # Verify data exists
    print_step("Verifying notes were created...")
    test_app_via_curl(ctx, f"{app_url}/notes", expected_content="First important note")
    print_success("Notes are stored in the application.")
    pause(ctx.pause_between_steps)

    # Create a backup
    print_header("Step 3: Create Backup")
    print_step(f"Creating backup of '{APP_NAME}'...")
    result = run_hop3(f"backup:create {APP_NAME}", check=False)

    backup_id = None
    if result.returncode != 0:
        print_error("Backup creation failed.")
        if result.stderr:
            print_info(f"  {result.stderr.strip()}")
        # Skip restore tests if backup failed
        cleanup_app(ctx, APP_NAME, app_url)
        msg = "Backup creation failed - cannot proceed with restore test"
        raise RuntimeError(msg)

    # Parse backup ID from output
    # Output format: "Backup ID: 20251207_143022_a8f3d9"
    if result.stdout:
        match = re.search(r"Backup ID:\s+(\S+)", result.stdout)
        if match:
            backup_id = match.group(1)
            print_success(f"Backup created: {backup_id}")

    if not backup_id:
        print_warning("Could not extract backup ID from output.")
        # Try to get it from backup:list
        list_result = run_hop3(f"backup:list {APP_NAME}", check=False, show=False)
        if list_result.stdout:
            # Look for backup ID in table output (first column after header)
            lines = list_result.stdout.strip().split("\n")
            for line in lines[2:]:  # Skip header lines
                parts = line.split()
                if parts and parts[0].startswith("20"):  # Backup IDs start with year
                    backup_id = parts[0]
                    print_info(f"  Found backup: {backup_id}")
                    break

    pause(ctx.pause_between_steps)

    # Show backup info
    if backup_id:
        print_header("Step 4: View Backup Information")
        print_step(f"Getting info for backup {backup_id}...")
        run_hop3(f"backup:info {backup_id}", check=False)
        pause(ctx.pause_between_steps)

    # Clear the data
    print_header("Step 5: Destroy Application Data")
    print_step("Clearing all notes from the application...")
    curl_request(ctx, f"{app_url}/notes/clear")
    print_info("  Notes cleared.")
    pause(ctx.pause_between_steps)

    # Verify data is gone
    print_step("Verifying notes are gone...")
    result = curl_request(ctx, f"{app_url}/notes")
    if result.returncode == 0 and '"count": 0' in result.stdout:
        print_success("Notes successfully cleared - count is 0.")
    else:
        print_info(f"  Response: {result.stdout[:100]}")
    pause(ctx.pause_between_steps)

    # Restore from backup
    if backup_id:
        print_header("Step 6: Restore from Backup")
        print_step(f"Restoring from backup {backup_id}...")
        result = run_hop3(f"backup:restore {backup_id}", check=False)

        if result.returncode != 0:
            print_warning("Restore may have encountered issues.")
            if result.stderr:
                print_info(f"  {result.stderr.strip()}")
        else:
            print_success("Restore completed.")
        pause(ctx.pause_between_steps)

        # Restart app to pick up restored data
        print_step("Restarting application to load restored data...")
        restart_app(ctx, APP_NAME)
        wait_for_app(seconds=3)

        # Verify data is restored
        print_header("Step 7: Verify Restored Data")
        print_step("Checking if notes were restored...")
        test_app_via_curl(ctx, f"{app_url}/notes", expected_content="First important note")
        print_success("Notes successfully restored from backup!")
        pause(ctx.pause_between_steps)
    else:
        print_warning("Skipping restore test - no backup ID available.")

    # Cleanup
    cleanup_app(ctx, APP_NAME, app_url)

    print_success("Demo 12 completed: Full backup and restore workflow demonstrated.")
