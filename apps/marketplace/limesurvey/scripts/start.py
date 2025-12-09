#!/usr/bin/env python3
"""LimeSurvey start script for Hop3."""

import base64
import os
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
MYSQL_USERNAME = os.environ.get("MYSQL_USERNAME", "limesurvey")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "limesurvey")

# Mail configuration
MAIL_FROM = os.environ.get("MAIL_FROM", "")
MAIL_FROM_DISPLAY_NAME = os.environ.get("MAIL_FROM_DISPLAY_NAME", "LimeSurvey")
SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
SMTP_PORT = os.environ.get("SMTP_PORT", "25")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

# LDAP configuration
LDAP_SERVER = os.environ.get("LDAP_SERVER", "")
LDAP_PORT = os.environ.get("LDAP_PORT", "389")
LDAP_USERS_BASE_DN = os.environ.get("LDAP_USERS_BASE_DN", "")
LDAP_BIND_DN = os.environ.get("LDAP_BIND_DN", "")
LDAP_BIND_PASSWORD = os.environ.get("LDAP_BIND_PASSWORD", "")


def run(cmd: list[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, check=check, **kwargs)


def mysql_cmd(query: str) -> subprocess.CompletedProcess:
    """Execute a MySQL query."""
    env = os.environ.copy()
    env["MYSQL_PWD"] = MYSQL_PASSWORD
    cmd = [
        "mysql",
        f"--user={MYSQL_USERNAME}",
        f"--host={MYSQL_HOST}",
        MYSQL_DATABASE,
        "-e",
        query,
    ]
    return run(cmd, check=False, capture_output=True, text=True, env=env)


def main() -> int:
    # Set MySQL password env var
    os.environ["MYSQL_PWD"] = MYSQL_PASSWORD

    # Create directories
    for d in [
        "/run/limesurvey/sessions",
        "/run/limesurvey/tmp/runtime",
        "/run/limesurvey/tmp/assets",
        "/run/limesurvey/tmp/upload",
    ]:
        Path(d).mkdir(parents=True, exist_ok=True)

    # Copy config
    shutil.copy(PKG_DIR / "config.php", "/run/limesurvey/config.php")

    # Ensure folders
    print("==> Ensure folders")
    (DATA_DIR / "upload").mkdir(parents=True, exist_ok=True)
    for d in ["upload/surveys", "upload/admintheme", "upload/themes/survey/generalfiles"]:
        (CODE_DIR / d).mkdir(parents=True, exist_ok=True)

    # Create php.ini if not exists
    php_ini = DATA_DIR / "php.ini"
    if not php_ini.exists():
        php_ini.write_text(
            "; Add custom PHP configuration in this file\n"
            "; Settings here are merged with the package's built-in php.ini\n\n"
        )

    # Change ownership
    print("==> Changing ownership")
    run(["chown", "-R", f"{HOP3_USER}:{HOP3_USER}", "/run/limesurvey", str(DATA_DIR)])

    # Check for first run
    security_file = DATA_DIR / "security.php"
    if not security_file.exists():
        print("==> Run installation script")
        run(
            [
                "sudo",
                "-E",
                "-u",
                HOP3_USER,
                "php",
                str(CODE_DIR / "application" / "commands" / "console.php"),
                "install",
                "admin",
                "changeme",
                "Administrator",
                "admin@server.local",
                "verbose",
            ]
        )
        mysql_cmd(
            "REPLACE INTO lime_settings_global (stg_name, stg_value) VALUES ('siteadminname', 'Administrator')"
        )
        if MAIL_FROM:
            mysql_cmd(
                f"UPDATE lime_surveys_groupsettings SET adminemail='{MAIL_FROM}' WHERE owner_id=1"
            )

    # Force SSL
    mysql_cmd(
        "REPLACE INTO lime_settings_global (stg_name, stg_value) VALUES ('force_ssl', 'on')"
    )

    # Configure email
    print("==> Configure email")
    if MAIL_FROM:
        mysql_cmd(
            f"REPLACE INTO lime_settings_global (stg_name, stg_value) VALUES ('siteadminemail', '{MAIL_FROM}')"
        )
        display_name_b64 = base64.b64encode(MAIL_FROM_DISPLAY_NAME.encode()).decode()
        mysql_cmd(
            f"REPLACE INTO lime_settings_global (stg_name, stg_value) VALUES ('siteadminname', FROM_BASE64('{display_name_b64}'))"
        )
        mysql_cmd(
            f"REPLACE INTO lime_settings_global (stg_name, stg_value) VALUES ('siteadminbounce', '{MAIL_FROM}')"
        )
        mysql_cmd(
            "REPLACE INTO lime_settings_global (stg_name, stg_value) VALUES ('emailmethod', 'smtp')"
        )
        mysql_cmd(
            "REPLACE INTO lime_settings_global (stg_name, stg_value) VALUES ('emailsmtpssl', '')"
        )
        mysql_cmd(
            f"REPLACE INTO lime_settings_global (stg_name, stg_value) VALUES ('emailsmtphost', '{SMTP_HOST}:{SMTP_PORT}')"
        )
        mysql_cmd(
            f"REPLACE INTO lime_settings_global (stg_name, stg_value) VALUES ('emailsmtpuser', '{SMTP_USERNAME}')"
        )

        # Encrypt password
        result = run(
            [
                "sudo",
                "-E",
                "-u",
                HOP3_USER,
                "php",
                str(CODE_DIR / "application" / "commands" / "console.php"),
                "encrypt",
                SMTP_PASSWORD,
            ],
            capture_output=True,
            text=True,
        )
        encrypted_password = result.stdout.strip()
        mysql_cmd(
            f"REPLACE INTO lime_settings_global (stg_name, stg_value) VALUES ('emailsmtppassword', '{encrypted_password}')"
        )
    else:
        print("==> app's mail delivery settings disabled not configuring email settings")

    # Configure LDAP
    if LDAP_SERVER:
        print("==> Configure LDAP plugin")
        result = mysql_cmd("SELECT id FROM lime_plugins WHERE name='AuthLDAP'")
        ldap_plugin_id = ""
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            if len(lines) > 1:
                ldap_plugin_id = lines[1].strip()

        if ldap_plugin_id:
            mysql_cmd(f"UPDATE lime_plugins SET active=1 WHERE id={ldap_plugin_id}")

            ldap_settings = {
                "server": f'"{LDAP_SERVER}"',
                "ldapport": f'"{LDAP_PORT}"',
                "ldapversion": '"2"',
                "ldapoptreferrals": '"0"',
                "ldaptls": "null",
                "ldapmode": '"searchandbind"',
                "userprefix": "null",
                "domainsuffix": "null",
                "searchuserattribute": '"username"',
                "usersearchbase": f'"{LDAP_USERS_BASE_DN}"',
                "extrauserfilter": '""',
                "binddn": f'"{LDAP_BIND_DN}"',
                "bindpwd": f'"{LDAP_BIND_PASSWORD}"',
                "mailattribute": '"mail"',
                "fullnameattribute": '"displayname"',
                "is_default": '"1"',
                "autocreate": '"1"',
                "automaticsurveycreation": '"1"',
                "groupsearchbase": '""',
                "groupsearchfilter": '""',
                "allowInitialUser": '"1"',
            }

            for key, value in ldap_settings.items():
                # Check if setting exists
                check = mysql_cmd(
                    f"SELECT * FROM lime_plugin_settings WHERE plugin_id={ldap_plugin_id} AND lime_plugin_settings.key='{key}'"
                )
                if not check.stdout.strip() or len(check.stdout.strip().split("\n")) <= 1:
                    print(f"  ==> Insert new ldap config {key} = {value}")
                    mysql_cmd(
                        f"INSERT INTO lime_plugin_settings (plugin_id, lime_plugin_settings.key, value) VALUES ({ldap_plugin_id}, '{key}', '{value}')"
                    )
                else:
                    print(f"  ==> Update ldap config {key} = {value}")
                    mysql_cmd(
                        f"UPDATE lime_plugin_settings SET value='{value}' WHERE plugin_id={ldap_plugin_id} AND lime_plugin_settings.key='{key}'"
                    )

    # Run database schema update
    print("==> Run database schema update")
    run(
        [
            "sudo",
            "-E",
            "-u",
            HOP3_USER,
            "php",
            str(CODE_DIR / "application" / "commands" / "console.php"),
            "updatedb",
        ]
    )

    # Start LimeSurvey
    print("==> Start LimeSurvey")
    pid_file = Path("/var/run/apache2/apache2.pid")
    if pid_file.exists():
        pid_file.unlink()

    os.execvp("/usr/sbin/apache2", ["/usr/sbin/apache2", "-DFOREGROUND"])


if __name__ == "__main__":
    sys.exit(main() or 0)
