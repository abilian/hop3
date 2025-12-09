#!/usr/bin/env python3
"""HedgeDoc start script for Hop3."""

import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

# Environment configuration
DATA_DIR = Path(os.environ.get("HOP3_DATA_DIR", "/app/data"))
CODE_DIR = Path(os.environ.get("HOP3_CODE_DIR", "/app/code"))
PKG_DIR = Path(os.environ.get("HOP3_PKG_DIR", "/app/pkg"))
HOP3_USER = os.environ.get("HOP3_USER", "www-data")
HOP3_GROUP = os.environ.get("HOP3_GROUP", "www-data")

# App configuration
HOP3_APP_DOMAIN = os.environ.get("HOP3_APP_DOMAIN", "localhost")
HOP3_USE_SSL = os.environ.get("HOP3_USE_SSL", "true")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# OIDC configuration
OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "")
OIDC_PROVIDER_NAME = os.environ.get("OIDC_PROVIDER_NAME", "SSO")
OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "")
OIDC_PROFILE_ENDPOINT = os.environ.get("OIDC_PROFILE_ENDPOINT", "")
OIDC_TOKEN_ENDPOINT = os.environ.get("OIDC_TOKEN_ENDPOINT", "")
OIDC_AUTH_ENDPOINT = os.environ.get("OIDC_AUTH_ENDPOINT", "")


def run(cmd: list[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, check=check, **kwargs)


def main() -> int:
    # Create directories
    (DATA_DIR / "uploads").mkdir(parents=True, exist_ok=True)
    Path("/tmp/codimd").mkdir(parents=True, exist_ok=True)
    Path("/run/codimd").mkdir(parents=True, exist_ok=True)

    config_file = DATA_DIR / "config.json"

    # Copy template on first run
    if not config_file.exists():
        print("==> Creating initial template on first run")
        shutil.copy(PKG_DIR / "templates" / "config.json.template", config_file)

    # Load and update config
    config = json.loads(config_file.read_text())

    # Initialize production section if needed
    if "production" not in config:
        config["production"] = {}

    # Generate and store session secret
    if config["production"].get("sessionSecret") is None:
        print("==> generating sessionSecret")
        session_secret = secrets.token_hex(32)
        config["production"]["sessionSecret"] = session_secret

        if not OIDC_ISSUER:
            print("==> enabling email login")
            config["production"]["allowEmailRegister"] = True
            config["production"]["email"] = True

        config_file.write_text(json.dumps(config, indent=2))

    # Set environment variables (these cannot be changed by user)
    os.environ["CMD_DOMAIN"] = HOP3_APP_DOMAIN
    os.environ["CMD_PROTOCOL_USESSL"] = HOP3_USE_SSL
    os.environ["CMD_DB_URL"] = DATABASE_URL
    os.environ["CMD_PORT"] = "3000"
    os.environ["CMD_TMP_PATH"] = "/tmp/codimd"

    # Configure OIDC if available
    if OIDC_ISSUER:
        print("==> configuring OIDC")
        os.environ["CMD_OAUTH2_PROVIDERNAME"] = OIDC_PROVIDER_NAME
        os.environ["CMD_OAUTH2_CLIENT_ID"] = OIDC_CLIENT_ID
        os.environ["CMD_OAUTH2_CLIENT_SECRET"] = OIDC_CLIENT_SECRET
        os.environ["CMD_OAUTH2_SCOPE"] = "openid email profile"
        os.environ["CMD_OAUTH2_USER_PROFILE_USERNAME_ATTR"] = "sub"
        os.environ["CMD_OAUTH2_USER_PROFILE_DISPLAY_NAME_ATTR"] = "name"
        os.environ["CMD_OAUTH2_USER_PROFILE_EMAIL_ATTR"] = "email"
        os.environ["CMD_OAUTH2_BASE_URL"] = OIDC_ISSUER
        os.environ["CMD_OAUTH2_USER_PROFILE_URL"] = OIDC_PROFILE_ENDPOINT
        os.environ["CMD_OAUTH2_TOKEN_URL"] = OIDC_TOKEN_ENDPOINT
        os.environ["CMD_OAUTH2_AUTHORIZATION_URL"] = OIDC_AUTH_ENDPOINT

    # Change permissions
    print("==> Changing permissions")
    run(
        [
            "chown",
            "-R",
            f"{HOP3_USER}:{HOP3_GROUP}",
            str(DATA_DIR),
            "/tmp/codimd",
            "/run/codimd",
        ]
    )

    # Start HedgeDoc
    print("==> Starting HedgeDoc")
    os.chdir(CODE_DIR)
    os.execvp("node", ["node", "app.js"])


if __name__ == "__main__":
    sys.exit(main() or 0)
