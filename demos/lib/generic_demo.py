# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Generic demo script for any Hop3 application.

This module provides a generic demo that works with any Hop3-compatible
application directory, without requiring a custom demo-script.py.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib.context import DemoContext


# Files that indicate a Hop3-compatible application
APP_INDICATORS = [
    "hop3.toml",  # Hop3 configuration
    "Dockerfile",  # Docker-based app
    "docker-compose.yml",  # Docker Compose app
    "requirements.txt",  # Python app
    "package.json",  # Node.js app
    "Procfile",  # Heroku-style app
    "Gemfile",  # Ruby app
    "go.mod",  # Go app
    "Cargo.toml",  # Rust app
]


def detect_app_type(app_dir: Path) -> str | None:
    """Detect the type of application based on files present.

    Returns:
        String describing the app type, or None if not detected.
    """
    if (app_dir / "hop3.toml").exists():
        # Check hop3.toml for builder type
        content = (app_dir / "hop3.toml").read_text()
        if 'builder = "docker"' in content or "builder = 'docker'" in content:
            return "Docker (hop3.toml)"
        return "Hop3 app"

    if (app_dir / "Dockerfile").exists():
        return "Docker"

    if (app_dir / "docker-compose.yml").exists():
        return "Docker Compose"

    if (app_dir / "requirements.txt").exists():
        return "Python"

    if (app_dir / "package.json").exists():
        return "Node.js"

    if (app_dir / "Procfile").exists():
        return "Procfile-based"

    if (app_dir / "Gemfile").exists():
        return "Ruby"

    if (app_dir / "go.mod").exists():
        return "Go"

    if (app_dir / "Cargo.toml").exists():
        return "Rust"

    return None


def is_hop3_app(app_dir: Path) -> bool:
    """Check if a directory contains a Hop3-compatible application."""
    return any((app_dir / indicator).exists() for indicator in APP_INDICATORS)


def sanitize_app_name(name: str) -> str:
    """Convert a directory name to a valid Hop3 app name.

    Hop3 app names should be lowercase alphanumeric with hyphens.
    """
    # Convert to lowercase
    name = name.lower()
    # Replace underscores and spaces with hyphens
    name = re.sub(r"[_\s]+", "-", name)
    # Remove any characters that aren't alphanumeric or hyphens
    name = re.sub(r"[^a-z0-9-]", "", name)
    # Remove leading/trailing hyphens
    name = name.strip("-")
    # Collapse multiple hyphens
    name = re.sub(r"-+", "-", name)
    # Ensure it's not empty
    if not name:
        name = "app"
    return name


def run_generic_demo(ctx: DemoContext, app_dir: Path) -> None:
    """Run a generic demo for any Hop3 application.

    Args:
        ctx: Demo context
        app_dir: Path to the application directory
    """
    from lib.app import (
        check_app_status,
        cleanup_app,
        deploy_app,
        redeploy_app,
        set_hostname,
        wait_for_app,
    )
    from lib.output import (
        bold,
        get_output_level,
        pause,
        print_blank,
        print_error,
        print_header,
        print_info,
        print_step,
        print_success,
    )

    # Validate the directory
    if not app_dir.exists():
        print_error(f"Directory not found: {app_dir}")
        msg = f"Directory not found: {app_dir}"
        raise RuntimeError(msg)

    if not app_dir.is_dir():
        print_error(f"Not a directory: {app_dir}")
        msg = f"Not a directory: {app_dir}"
        raise RuntimeError(msg)

    # Detect app type
    app_type = detect_app_type(app_dir)
    if not app_type:
        print_error(f"No Hop3-compatible application found in: {app_dir}")
        print_info("Expected one of: " + ", ".join(APP_INDICATORS))
        msg = f"Not a Hop3-compatible application: {app_dir}"
        raise RuntimeError(msg)

    # Derive app name from directory
    app_name = sanitize_app_name(app_dir.name)
    # Use the server hostname for all apps (from --host argument)
    app_hostname = ctx.hostname
    app_url = f"https://{app_hostname}"

    # Print header and details (skip in quiet mode)
    print_header(f"Generic Demo: {app_dir.name}")
    if get_output_level() >= 2:  # NORMAL or VERBOSE
        print_blank()
        print(f"  {bold('Application:')} {app_dir}")
        print(f"  {bold('Type:')}        {app_type}")
        print(f"  {bold('App name:')}    {app_name}")
        print(f"  {bold('Hostname:')}    {app_hostname}")
        print_blank()
    pause(ctx.pause_between_steps)

    # Show directory contents (skip in quiet mode)
    print_step("Application files:")
    if get_output_level() >= 2:  # NORMAL or VERBOSE
        print_blank()
        files = sorted(app_dir.iterdir())
        for f in files[:10]:  # Limit to first 10 files
            icon = "📁" if f.is_dir() else "📄"
            print(f"  {icon} {f.name}")
        if len(files) > 10:
            print(f"  ... and {len(files) - 10} more files")
        print_blank()
    pause(ctx.pause_between_steps)

    # Deploy
    deploy_app(ctx, app_name, app_dir)

    # Set hostname
    set_hostname(ctx, app_name, app_hostname)

    # Redeploy to apply hostname
    redeploy_app(ctx, app_name, app_dir)

    # Wait for app
    wait_seconds = 5 if "Docker" in app_type else 3
    wait_for_app(seconds=wait_seconds)

    # Check status
    check_app_status(ctx, app_name)

    # Test the application
    print_header("Testing Application")

    print_step(f"Application should be available at: {app_url}")
    print_info("Note: DNS must resolve to the server for external access.")
    print_info(
        f"You can test locally with: curl -sk --resolve {app_hostname}:443:{ctx.server_ip} {app_url}/"
    )
    pause(ctx.pause_between_steps)

    # Cleanup
    cleanup_app(ctx, app_name, app_url)

    print_success(f"Generic demo completed for: {app_dir.name}")
