#!/usr/bin/env python3
"""OpenCloud start script for Hop3."""

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

# Environment configuration
DATA_DIR = Path(os.environ.get("HOP3_DATA_DIR", "/app/data"))
CODE_DIR = Path(os.environ.get("HOP3_CODE_DIR", "/app/code"))
HOP3_USER = os.environ.get("HOP3_USER", "www-data")

# App configuration
HOP3_APP_DOMAIN = os.environ.get("HOP3_APP_DOMAIN", "localhost")
HOP3_APP_ORIGIN = os.environ.get("HOP3_APP_ORIGIN", "http://localhost")

# SMTP configuration
SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
SMTP_STARTTLS_PORT = os.environ.get("SMTP_STARTTLS_PORT", "587")
MAIL_FROM_DISPLAY_NAME = os.environ.get("MAIL_FROM_DISPLAY_NAME", "OpenCloud")
MAIL_FROM = os.environ.get("MAIL_FROM", "noreply@localhost")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

# OIDC configuration
OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "")
OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "")


def run(cmd: list[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, check=check, **kwargs)


def main() -> int:
    # Create directories
    (DATA_DIR / "data").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "config").mkdir(parents=True, exist_ok=True)

    # Change ownership
    run(["chown", "-R", f"{HOP3_USER}:{HOP3_USER}", str(DATA_DIR)])

    # Initialize OpenCloud if not done
    config_file = DATA_DIR / "config" / "opencloud.yaml"
    if not config_file.exists():
        print("==> Init OpenCloud")
        opencloud_bin = CODE_DIR / "opencloud"
        run(
            [
                "su",
                "-s",
                "/bin/bash",
                HOP3_USER,
                "-c",
                f"{opencloud_bin} init --insecure true --admin-password changeme",
            ]
        )

    # Set environment variables
    os.environ["OC_DOMAIN"] = HOP3_APP_DOMAIN
    os.environ["OC_URL"] = HOP3_APP_ORIGIN
    os.environ["OC_INSECURE"] = "true"
    os.environ["PROXY_TLS"] = "false"

    # Enable notifications service
    os.environ["OC_ADD_RUN_SERVICES"] = "notifications"

    # SMTP configuration
    os.environ["NOTIFICATIONS_SMTP_HOST"] = SMTP_HOST
    os.environ["NOTIFICATIONS_SMTP_PORT"] = SMTP_STARTTLS_PORT
    os.environ["NOTIFICATIONS_SMTP_SENDER"] = f"{MAIL_FROM_DISPLAY_NAME} <{MAIL_FROM}>"
    os.environ["NOTIFICATIONS_SMTP_USERNAME"] = SMTP_USERNAME
    os.environ["NOTIFICATIONS_SMTP_PASSWORD"] = SMTP_PASSWORD
    os.environ["NOTIFICATIONS_SMTP_AUTHENTICATION"] = "login"
    os.environ["NOTIFICATIONS_SMTP_ENCRYPTION"] = "starttls"
    os.environ["NOTIFICATIONS_SMTP_INSECURE"] = "false"

    # OIDC configuration
    if OIDC_ISSUER:
        os.environ["PROXY_AUTOPROVISION_ACCOUNTS"] = "true"
        os.environ["OC_OIDC_ISSUER"] = OIDC_ISSUER
        # Extract domain from OIDC issuer
        parsed = urlparse(OIDC_ISSUER)
        os.environ["IDP_DOMAIN"] = parsed.netloc
        os.environ["OC_EXCLUDE_RUN_SERVICES"] = "idp,idm"  # disable built-in idp
        os.environ["WEB_OIDC_CLIENT_ID"] = OIDC_CLIENT_ID
        os.environ["PROXY_OIDC_REWRITE_WELLKNOWN"] = "true"
        os.environ["PROXY_ROLE_ASSIGNMENT_DRIVER"] = "oidc"
        os.environ["PROXY_USER_OIDC_CLAIM"] = "sub"
        os.environ["PROXY_OIDC_ACCESS_TOKEN_VERIFY_METHOD"] = "none"

    # Start OpenCloud
    print("==> Starting OpenCloud")
    opencloud_bin = CODE_DIR / "opencloud"
    os.execvp(
        "su",
        [
            "su",
            "-s",
            "/bin/bash",
            HOP3_USER,
            "-c",
            f"{opencloud_bin} server",
        ],
    )


if __name__ == "__main__":
    sys.exit(main() or 0)
