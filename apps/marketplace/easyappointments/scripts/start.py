#!/usr/bin/env python3
"""Easy!Appointments start script for Hop3."""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Environment configuration
DATA_DIR = Path(os.environ.get("HOP3_DATA_DIR", "/app/data"))
CODE_DIR = Path(os.environ.get("HOP3_CODE_DIR", "/app/code"))
PKG_DIR = Path(os.environ.get("HOP3_PKG_DIR", "/app/pkg"))
HOP3_USER = os.environ.get("HOP3_USER", "www-data")

# MySQL configuration
MYSQL_USERNAME = os.environ.get("MYSQL_USERNAME", "easyappointments")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_PORT = os.environ.get("MYSQL_PORT", "3306")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "easyappointments")

# App configuration
HOP3_APP_ORIGIN = os.environ.get("HOP3_APP_ORIGIN", "http://localhost")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
MAIL_FROM_DISPLAY_NAME = os.environ.get("MAIL_FROM_DISPLAY_NAME", "Easy!Appointments")


def run(cmd: list[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, check=check, **kwargs)


def mysql_cmd(query: str) -> subprocess.CompletedProcess:
    """Execute a MySQL query."""
    cmd = [
        "mysql",
        "-u",
        MYSQL_USERNAME,
        f"-p{MYSQL_PASSWORD}",
        "-h",
        MYSQL_HOST,
        "--port",
        MYSQL_PORT,
        "--database",
        MYSQL_DATABASE,
        "-e",
        query,
    ]
    return run(cmd, check=False, capture_output=True, text=True)


def main() -> int:
    print("=> Ensure directories")
    Path("/run/easyappointments/sessions").mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    Path("/run/easyappointments/logs").mkdir(parents=True, exist_ok=True)

    # Create php.ini if not exists
    php_ini = DATA_DIR / "php.ini"
    if not php_ini.exists():
        php_ini.write_text(
            "; Add custom PHP configuration in this file\n"
            "; Settings here are merged with the package's built-in php.ini\n\n"
        )

    # Copy config sample if not exists
    config_file = DATA_DIR / "config.php"
    if not config_file.exists():
        print("=> Ensure config.php")
        shutil.copy(PKG_DIR / "config-sample.php", config_file)

    # Patch config.php
    print("=> Patch config.php")
    content = config_file.read_text()
    replacements = [
        (r"const BASE_URL.*", f"const BASE_URL = '{HOP3_APP_ORIGIN}';"),
        (r"const DB_HOST.*", f"const DB_HOST = '{MYSQL_HOST}';"),
        (r"const DB_NAME.*", f"const DB_NAME = '{MYSQL_DATABASE}';"),
        (r"const DB_USERNAME.*", f"const DB_USERNAME = '{MYSQL_USERNAME}';"),
        (r"const DB_PASSWORD.*", f"const DB_PASSWORD = '{MYSQL_PASSWORD}';"),
    ]
    for pattern, replacement in replacements:
        content = re.sub(pattern, replacement, content)
    config_file.write_text(content)

    # Check if database is empty
    result = mysql_cmd(
        f"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = '{MYSQL_DATABASE}';"
    )
    table_count = "0"
    if result.returncode == 0:
        # Parse the count from output
        lines = result.stdout.strip().split("\n")
        if len(lines) > 1:
            table_count = lines[1].strip()

    if table_count == "0":
        print("=> Initial setup")
        run(
            [
                "sudo",
                "-E",
                "-u",
                HOP3_USER,
                "php",
                str(CODE_DIR / "index.php"),
                "console",
                "install",
            ]
        )
    else:
        print("=> Migrate database")
        run(
            [
                "sudo",
                "-E",
                "-u",
                HOP3_USER,
                "php",
                str(CODE_DIR / "index.php"),
                "console",
                "migrate",
            ]
        )

    # Update company settings
    print("=> Ensure company email and name")
    mysql_cmd(
        f"UPDATE ea_settings SET value='{SMTP_USERNAME}' WHERE name='company_email'"
    )
    mysql_cmd(
        f"UPDATE ea_settings SET value='{MAIL_FROM_DISPLAY_NAME}' WHERE name='company_name'"
    )

    # Ensure permissions
    print("=> Ensure permissions")
    run(
        [
            "chown",
            "-R",
            f"{HOP3_USER}:{HOP3_USER}",
            str(DATA_DIR),
            "/run/easyappointments",
        ]
    )

    # Start apache
    print("=> Starting apache")
    # Remove PID file if exists
    pid_file = Path("/var/run/apache2/apache2.pid")
    if pid_file.exists():
        pid_file.unlink()

    os.execvp("/usr/sbin/apache2", ["/usr/sbin/apache2", "-DFOREGROUND"])


if __name__ == "__main__":
    sys.exit(main() or 0)
