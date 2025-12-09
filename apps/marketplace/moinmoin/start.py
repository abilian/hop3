#!/usr/bin/env python3
"""Startup script for MoinMoin Wiki."""

import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    print("==> Starting MoinMoin Wiki")

    port = os.environ.get("PORT", "8080")

    # Initialize wiki if not already done
    wiki_data = Path("/app/wiki")
    if not wiki_data.exists():
        print("==> Initializing new wiki")
        subprocess.run(["./m", "new-wiki"], check=True)

    # Start with Gunicorn
    print(f"==> Starting Gunicorn on port {port}")
    os.execvp(
        "gunicorn",
        ["gunicorn", "-b", f"0.0.0.0:{port}", "--workers", "2", "moin:app"],
    )


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
