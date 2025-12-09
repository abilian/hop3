#!/usr/bin/env python3
"""Radicale start script for Hop3."""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Environment configuration
CODE_DIR = Path(os.environ.get("HOP3_CODE_DIR", "/app/code"))
DATA_DIR = Path(os.environ.get("HOP3_DATA_DIR", "/app/data"))
PKG_DIR = Path(os.environ.get("HOP3_PKG_DIR", "/app/pkg"))
HOP3_USER = os.environ.get("HOP3_USER", "www-data")

# LDAP configuration
LDAP_HOST = os.environ.get("LDAP_HOST", "localhost")
LDAP_PORT = os.environ.get("LDAP_PORT", "389")
LDAP_USERS_BASE_DN = os.environ.get("LDAP_USERS_BASE_DN", "ou=users,dc=example")
LDAP_BIND_DN = os.environ.get("LDAP_BIND_DN", "")
LDAP_BIND_PASSWORD = os.environ.get("LDAP_BIND_PASSWORD", "")


def run(cmd: list[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, check=check, **kwargs)


def main() -> int:
    os.chdir(CODE_DIR)

    # Create directories
    (DATA_DIR / "collections").mkdir(parents=True, exist_ok=True)

    # Update radicale config
    print("==> Update radicale config")
    config_template = PKG_DIR / "conf" / "config"
    content = config_template.read_text()

    # Replace LDAP settings
    content = re.sub(
        r"ldap_uri = ldap://.*",
        f"ldap_uri = ldap://{LDAP_HOST}:{LDAP_PORT}/",
        content,
    )
    content = re.sub(r"ldap_base = .*", f"ldap_base = {LDAP_USERS_BASE_DN}", content)
    content = re.sub(r"ldap_reader_dn = .*", f"ldap_reader_dn = {LDAP_BIND_DN}", content)
    content = re.sub(r"ldap_secret = .*", f"ldap_secret = {LDAP_BIND_PASSWORD}", content)

    Path("/run/config").write_text(content)

    # Copy default rights file if not exists
    rights_file = DATA_DIR / "rights"
    if not rights_file.exists():
        print("==> Copy default /app/data/rights file")
        shutil.copy(PKG_DIR / "templates" / "rights.template", rights_file)

    # Ensure folder permissions
    print("==> Ensure folder permissions")
    run(["chown", "-R", f"{HOP3_USER}:{HOP3_USER}", str(DATA_DIR)])

    # Start radicale
    print("==> Start radicale")
    venv_activate = CODE_DIR / "venv" / "bin" / "activate"
    os.execvp(
        "su",
        [
            "su",
            "-s",
            "/bin/bash",
            HOP3_USER,
            "-c",
            f"source {venv_activate} && radicale --config /run/config",
        ],
    )


if __name__ == "__main__":
    sys.exit(main() or 0)
