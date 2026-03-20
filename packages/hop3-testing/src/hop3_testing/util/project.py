# Copyright (c) 2024-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Project root detection utilities."""

from __future__ import annotations

import os
from pathlib import Path


def find_project_root() -> Path:
    """Find the Hop3 project root directory.

    Searches for the monorepo root by:
    1. Checking HOP3_PROJECT_ROOT environment variable
    2. Looking for monorepo markers (apps/test-apps + packages/hop3-server)
    3. Looking for pyproject.toml with hop3 workspace markers

    Returns:
        Path to the project root, or current directory as fallback.
    """
    # Check environment variable first
    if hop3_root := os.environ.get("HOP3_PROJECT_ROOT"):
        return Path(hop3_root)

    # Try to find by looking for the hop3 monorepo structure
    # Start from current directory and go up
    current = Path.cwd()
    for _ in range(10):
        # Look for the monorepo markers: apps/test-apps and packages/hop3-server
        if (current / "apps" / "test-apps").exists() and (
            current / "packages" / "hop3-server"
        ).exists():
            return current

        # Also check for pyproject.toml with hop3 workspace
        pyproject = current / "pyproject.toml"
        if pyproject.exists():
            content = pyproject.read_text()
            if "hop3-server" in content and "hop3-cli" in content:
                return current

        parent = current.parent
        if parent == current:
            break
        current = parent

    # Fallback to current directory
    return Path.cwd()


def find_project_root_optional() -> Path | None:
    """Find the Hop3 project root directory, returning None if not found.

    Same as find_project_root() but returns None instead of falling back
    to current directory.

    Returns:
        Path to the project root, or None if not found.
    """
    # Check environment variable first
    if hop3_root := os.environ.get("HOP3_PROJECT_ROOT"):
        return Path(hop3_root)

    # Try to find by looking for the hop3 monorepo structure
    current = Path.cwd()
    for _ in range(10):
        if (current / "apps" / "test-apps").exists() and (
            current / "packages" / "hop3-server"
        ).exists():
            return current

        pyproject = current / "pyproject.toml"
        if pyproject.exists():
            content = pyproject.read_text()
            if "hop3-server" in content and "hop3-cli" in content:
                return current

        parent = current.parent
        if parent == current:
            break
        current = parent

    return None
