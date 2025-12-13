#!/usr/bin/env python3
"""Startup script for OpenCloud."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    Path("/app/data").mkdir(parents=True, exist_ok=True)
    Path("/app/config").mkdir(parents=True, exist_ok=True)

    # Initialize OpenCloud if not already done
    config_file = Path("/app/config/opencloud.yaml")
    if not config_file.exists():
        print("==> Initializing OpenCloud")
        admin_password = os.environ.get("ADMIN_PASSWORD", "admin")
        subprocess.run(
            ["/app/opencloud", "init", "--insecure", "true", "--admin-password", admin_password],
            check=True,
        )

    # Configure OpenCloud
    host_name = os.environ.get("HOST_NAME", "localhost")
    os.environ["OC_DOMAIN"] = host_name
    os.environ["OC_URL"] = f"https://{host_name}"
    os.environ["OC_INSECURE"] = "true"
    os.environ["PROXY_TLS"] = "false"

    # Disable notifications service (requires SMTP configuration)
    # To enable notifications, set NOTIFICATIONS_SMTP_* environment variables
    # os.environ["OC_ADD_RUN_SERVICES"] = "notifications"

    admin_password = os.environ.get("ADMIN_PASSWORD", "admin")
    print("==> Starting OpenCloud on port 9200")
    print(f"    Domain: {os.environ['OC_DOMAIN']}")
    print(f"    URL: {os.environ['OC_URL']}")
    print(f"    Admin password: {admin_password}")

    os.execvp("/app/opencloud", ["/app/opencloud", "server"])


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
