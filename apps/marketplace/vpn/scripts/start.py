#!/usr/bin/env python3
"""VPN start script for Hop3."""

import os
import subprocess
import sys
from pathlib import Path

# Environment configuration
DATA_DIR = Path(os.environ.get("HOP3_DATA_DIR", "/app/data"))
VPN_USER = os.environ.get("VPN_USER", "vpn")

# App configuration
HOP3_APP_ORIGIN = os.environ.get("HOP3_APP_ORIGIN", "http://localhost:3000")
HOP3_APP_DOMAIN = os.environ.get("HOP3_APP_DOMAIN", "localhost")


def run(cmd: list[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, check=check, **kwargs)


def main() -> int:
    # Create directories
    Path("/run/vpn").mkdir(parents=True, exist_ok=True)
    Path("/run/dnsmasq/hosts").mkdir(parents=True, exist_ok=True)

    # Set environment variables
    os.environ["APP_ORIGIN"] = HOP3_APP_ORIGIN
    os.environ["APP_DOMAIN"] = HOP3_APP_DOMAIN
    os.environ["DATA_DIR"] = str(DATA_DIR)
    os.environ["RUN_DIR"] = "/run/vpn"
    os.environ["SERVER_NAME"] = "hop3"
    os.environ["VPN_USER"] = VPN_USER

    # Fix permissions
    print("==> Fixing permissions")
    run(["chown", "-R", f"{VPN_USER}:{VPN_USER}", str(DATA_DIR), "/run/vpn"])

    # Start VPN
    print("Starting VPN")
    os.execvp(
        "/usr/bin/supervisord",
        [
            "/usr/bin/supervisord",
            "--configuration",
            "/etc/supervisor/supervisord.conf",
            "--nodaemon",
            "-i",
            "OpenVPN",
        ],
    )


if __name__ == "__main__":
    sys.exit(main() or 0)
