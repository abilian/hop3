#!/usr/bin/env python3
"""Kanboard start script for Hop3."""

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

# MySQL configuration
MYSQL_USERNAME = os.environ.get("MYSQL_USERNAME", "kanboard")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_PORT = os.environ.get("MYSQL_PORT", "3306")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "kanboard")

# Mail configuration
MAIL_FROM = os.environ.get("MAIL_FROM", "noreply@localhost")
SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
SMTP_PORT = os.environ.get("SMTP_PORT", "25")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

# App configuration
HOP3_APP_ORIGIN = os.environ.get("HOP3_APP_ORIGIN", "http://localhost")

# OIDC configuration
OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "")
OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "")
OIDC_AUTH_ENDPOINT = os.environ.get("OIDC_AUTH_ENDPOINT", "")
OIDC_TOKEN_ENDPOINT = os.environ.get("OIDC_TOKEN_ENDPOINT", "")
OIDC_PROFILE_ENDPOINT = os.environ.get("OIDC_PROFILE_ENDPOINT", "")


def run(cmd: list[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, check=check, **kwargs)


def mysql_cmd(query: str) -> subprocess.CompletedProcess:
    """Execute a MySQL query."""
    cmd = [
        "mysql",
        f"--defaults-file=/run/kanboard/mysql-extra",
        f"--user={MYSQL_USERNAME}",
        f"--host={MYSQL_HOST}",
        "-P",
        MYSQL_PORT,
        MYSQL_DATABASE,
        "-e",
        query,
    ]
    return run(cmd, check=False, capture_output=True, text=True)


def setup_application_url():
    """Update application URL in database."""
    result = mysql_cmd(
        f'REPLACE INTO settings (`option`, `value`) VALUES ("application_url", "{HOP3_APP_ORIGIN}/")'
    )
    if result.returncode == 0:
        print("==> Application URL updated")
    else:
        print("==> Failed to set application url")


def setup_oidc():
    """Configure OIDC settings."""
    print("==> Ensure OIDC settings")

    # Copy OAuth2 plugin
    oauth2_src = CODE_DIR / "plugins.orig" / "OAuth2"
    oauth2_dest = DATA_DIR / "plugins" / "OAuth2"
    if oauth2_src.exists():
        if oauth2_dest.exists():
            shutil.rmtree(oauth2_dest)
        shutil.copytree(oauth2_src, oauth2_dest)

    # OIDC settings SQL
    oidc_settings = [
        ('oauth2_account_creation', '1'),
        ('oauth2_authorize_url', OIDC_AUTH_ENDPOINT),
        ('oauth2_client_id', OIDC_CLIENT_ID),
        ('oauth2_client_secret', OIDC_CLIENT_SECRET),
        ('oauth2_email_domains', ''),
        ('oauth2_key_email', 'email'),
        ('oauth2_key_group_filter', ''),
        ('oauth2_key_groups', ''),
        ('oauth2_key_name', 'name'),
        ('oauth2_key_user_id', 'sub'),
        ('oauth2_key_username', 'preferred_username'),
        ('oauth2_scopes', 'openid profile email'),
        ('oauth2_token_url', OIDC_TOKEN_ENDPOINT),
        ('oauth2_user_api_url', OIDC_PROFILE_ENDPOINT),
    ]

    for key, value in oidc_settings:
        mysql_cmd(f'REPLACE INTO settings (`option`, `value`) VALUES ("{key}", "{value}")')


def main() -> int:
    # Create directories
    for d in ["plugins", "data"]:
        (DATA_DIR / d).mkdir(parents=True, exist_ok=True)
    Path("/run/kanboard/sessions").mkdir(parents=True, exist_ok=True)

    # Create MySQL credentials file
    mysql_extra = Path("/run/kanboard/mysql-extra")
    mysql_extra.write_text(f"[client]\npassword={MYSQL_PASSWORD}\n")

    # Generate config from template
    template_content = (PKG_DIR / "templates" / "config.php.template").read_text()
    replacements = {
        "##MAIL_FROM##": MAIL_FROM,
        "##SMTP_HOST##": SMTP_HOST,
        "##SMTP_PORT##": SMTP_PORT,
        "##SMTP_USERNAME##": SMTP_USERNAME,
        "##SMTP_PASSWORD##": SMTP_PASSWORD,
        "##MYSQL_USERNAME##": MYSQL_USERNAME,
        "##MYSQL_PASSWORD##": MYSQL_PASSWORD,
        "##MYSQL_HOST##": MYSQL_HOST,
        "##MYSQL_PORT##": MYSQL_PORT,
        "##MYSQL_DATABASE##": MYSQL_DATABASE,
    }
    for pattern, replacement in replacements.items():
        template_content = template_content.replace(pattern, replacement)
    Path("/run/kanboard/config.php").write_text(template_content)

    # Create php.ini if not exists
    php_ini = DATA_DIR / "php.ini"
    if not php_ini.exists():
        php_ini.write_text(
            "; Add custom PHP configuration in this file\n"
            "; Settings here are merged with the package's built-in php.ini\n\n"
        )

    # Copy custom config template if not exists
    custom_config = DATA_DIR / "customconfig.php"
    if not custom_config.exists():
        print("==> Copying customconfig.php.template")
        shutil.copy(
            PKG_DIR / "templates" / "customconfig.php.template", custom_config
        )

    # Check if database is empty
    result = mysql_cmd(
        f"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = '{MYSQL_DATABASE}';"
    )
    table_count = "0"
    if result.returncode == 0:
        lines = result.stdout.strip().split("\n")
        if len(lines) > 1:
            table_count = lines[1].strip()

    if table_count == "0":
        print("==> Initializing database")
        schema_file = CODE_DIR / "app" / "Schema" / "Sql" / "mysql.sql"
        with open(schema_file) as f:
            schema_sql = f.read()
        # Run schema SQL
        run(
            [
                "mysql",
                f"--defaults-file=/run/kanboard/mysql-extra",
                f"--user={MYSQL_USERNAME}",
                f"--host={MYSQL_HOST}",
                "-P",
                MYSQL_PORT,
                MYSQL_DATABASE,
            ],
            input=schema_sql,
            text=True,
            check=False,
        )

    # Run migrations
    print("==> Migrating database")
    run(["php", str(CODE_DIR / "cli"), "db:migrate"])

    # Setup application URL
    setup_application_url()

    # Setup OIDC if configured
    if OIDC_ISSUER:
        setup_oidc()

    # Change ownership
    run(["chown", "-R", "www-data:www-data", str(DATA_DIR), "/run/kanboard"])

    # Start apache
    print("==> Starting apache")
    pid_file = Path("/var/run/apache2/apache2.pid")
    if pid_file.exists():
        pid_file.unlink()

    os.execvp("/usr/sbin/apache2", ["/usr/sbin/apache2", "-DFOREGROUND"])


if __name__ == "__main__":
    sys.exit(main() or 0)
