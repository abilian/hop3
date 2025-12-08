#!/usr/bin/env python
# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Pre-build hook script.

This script runs BEFORE the main build process.
Use cases:
- Install build-time dependencies
- Run linters or type checkers
- Validate configuration files
- Download external assets
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path


def main():
    print("=" * 50)
    print("PRE-BUILD HOOK: Starting...")
    print("=" * 50)

    # Create build info file
    build_info = Path(__file__).parent.parent / "build_info.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    info_content = f"""Build Information
=================
Pre-build started: {timestamp}
Python version: {sys.version}
"""

    build_info.write_text(info_content)
    print(f"Created build info file: {build_info}")

    # Simulate checking dependencies
    print("Checking Python environment...")
    print("  - Flask: OK")
    print("  - Gunicorn: OK")

    print("PRE-BUILD HOOK: Completed successfully!")
    print("=" * 50)


if __name__ == "__main__":
    main()
