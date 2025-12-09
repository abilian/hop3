#!/usr/bin/env python3
"""Startup script for DokuWiki."""

import os
import subprocess
import sys


def main() -> None:
    print("==> Starting DokuWiki")

    # Ensure data directories are writable
    subprocess.run(
        [
            "chown",
            "-R",
            "www-data:www-data",
            "/var/www/html/data",
            "/var/www/html/conf",
            "/var/www/html/lib/plugins",
        ],
        check=True,
    )

    print("==> Starting Apache")
    os.execvp("apache2-foreground", ["apache2-foreground"])


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
