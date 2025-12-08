#!/usr/bin/env python
# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Pre-run hook script.

This script runs BEFORE the application starts.
Use cases:
- Run database migrations
- Warm up caches
- Validate environment variables
- Check external service connectivity
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path


def main():
    print("=" * 50)
    print("PRE-RUN HOOK: Starting...")
    print("=" * 50)

    # Update build info with runtime info
    build_info = Path(__file__).parent.parent / "build_info.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if build_info.exists():
        content = build_info.read_text()
        content += f"Pre-run executed: {timestamp}\n"
        content += f"PORT: {os.environ.get('PORT', 'not set')}\n"
        content += f"APP_ENV: {os.environ.get('APP_ENV', 'not set')}\n"
        build_info.write_text(content)

    # Simulate database migration check
    print("Checking database migrations...")
    print("  - No pending migrations")

    # Validate environment
    print("Validating environment...")
    required_vars = ["PORT"]
    for var in required_vars:
        value = os.environ.get(var)
        status = "OK" if value else "MISSING"
        print(f"  - {var}: {status}")

    print("PRE-RUN HOOK: Completed successfully!")
    print("=" * 50)


if __name__ == "__main__":
    main()
