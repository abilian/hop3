#!/usr/bin/env python
# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Post-build hook script.

This script runs AFTER the main build process.
Use cases:
- Compile/minify CSS/JS assets
- Generate static files
- Run database migrations (for build-time schemas)
- Create cache files
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def main():
    print("=" * 50)
    print("POST-BUILD HOOK: Starting...")
    print("=" * 50)

    # Update build info
    build_info = Path(__file__).parent.parent / "build_info.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if build_info.exists():
        content = build_info.read_text()
        content += f"Post-build completed: {timestamp}\n"
        build_info.write_text(content)

    # Simulate asset compilation
    print("Compiling assets...")
    static_dir = Path(__file__).parent.parent / "static"
    static_dir.mkdir(exist_ok=True)

    # Create a "minified" CSS file
    css_content = """/* Compiled by post-build hook */
body { font-family: sans-serif; margin: 0; padding: 20px; }
h1 { color: #333; }
.container { max-width: 800px; margin: 0 auto; }
"""
    (static_dir / "app.min.css").write_text(css_content)
    print(f"  Created: {static_dir / 'app.min.css'}")

    print("POST-BUILD HOOK: Completed successfully!")
    print("=" * 50)


if __name__ == "__main__":
    main()
