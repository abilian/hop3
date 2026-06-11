#!/usr/bin/env python3
"""Startup script for Filebrowser."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    print("==> Starting Filebrowser")

    # Create database directory if needed
    db_dir = Path("/app/database")
    db_dir.mkdir(parents=True, exist_ok=True)

    db_path = db_dir / "filebrowser.db"

    # Initialize database if it doesn't exist
    if not db_path.exists():
        print("==> Initializing Filebrowser database...")
        subprocess.run(
            [
                "/app/filebrowser",
                "config",
                "init",
                "--database",
                str(db_path),
            ],
            check=True,
        )
        subprocess.run(
            [
                "/app/filebrowser",
                "users",
                "add",
                "admin",
                "admin",
                "--database",
                str(db_path),
                "--perm.admin",
            ],
            check=True,
        )

    print("==> Starting Filebrowser server...")
    os.execvp(
        "/app/filebrowser",
        [
            "/app/filebrowser",
            "--database",
            str(db_path),
            "--root",
            "/srv",
            "--address",
            "0.0.0.0",
            "--port",
            "8080",
        ],
    )


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
