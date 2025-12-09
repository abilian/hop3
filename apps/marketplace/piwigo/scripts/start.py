#!/usr/bin/env python3
"""Piwigo start script for Hop3."""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Environment configuration
DATA_DIR = Path(os.environ.get("HOP3_DATA_DIR", "/app/data"))
CODE_DIR = Path(os.environ.get("HOP3_CODE_DIR", "/app/code"))
HOP3_USER = os.environ.get("HOP3_USER", "www-data")

# MySQL configuration
MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_USERNAME = os.environ.get("MYSQL_USERNAME", "piwigo")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "piwigo")

# Mail configuration
MAIL_FROM_DISPLAY_NAME = os.environ.get("MAIL_FROM_DISPLAY_NAME", "Piwigo")
MAIL_FROM = os.environ.get("MAIL_FROM", "")
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = os.environ.get("SMTP_PORT", "")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")


def run(cmd: list[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, check=check, **kwargs)


def setup():
    """Setup Piwigo on first run (runs in background after apache starts)."""
    dummy_file = DATA_DIR / "_data" / "dummy.txt"
    if not dummy_file.exists():
        print("=> Detected first run")
        for src_name, dest_name in [
            ("_plugins", "plugins"),
            ("_themes", "themes"),
            ("_language", "language"),
            ("_local", "local"),
        ]:
            src = CODE_DIR / src_name
            dest = DATA_DIR / dest_name
            if src.exists():
                for item in src.iterdir():
                    dest_item = dest / item.name
                    if item.is_dir():
                        if dest_item.exists():
                            shutil.rmtree(dest_item)
                        shutil.copytree(item, dest_item)
                    else:
                        shutil.copy(item, dest_item)

        # Copy dummy file
        dummy_src = CODE_DIR / "_data_old" / "dummy.txt"
        if dummy_src.exists():
            shutil.copy(dummy_src, dummy_file)

    # Wait for apache to start
    pid_file = Path("/var/run/apache2/apache2.pid")
    while not pid_file.exists():
        print("=> Waiting for apache2 to start")
        time.sleep(3)

    # Fixup permissions
    print("=> Fixup permissions")
    run(["chown", "-R", f"{HOP3_USER}:{HOP3_USER}", str(DATA_DIR), "/run/piwigo"])

    # Setup piwigo via HTTP
    print("=> Setup piwigo")
    install_data = (
        f"?language=en_UK&install=true&dbhost={MYSQL_HOST}"
        f"&dbuser={MYSQL_USERNAME}&dbpasswd={MYSQL_PASSWORD}&dbname={MYSQL_DATABASE}"
        f"&admin_name=admin&admin_pass1=changeme&admin_pass2=changeme&admin_mail=admin@cloudron.local"
    )

    run(
        [
            "curl",
            "-L",
            "-X",
            "POST",
            "--data",
            install_data,
            "http://localhost:8000/install.php",
        ],
        check=False,
    )

    # Update database config to use environment variables
    db_config = DATA_DIR / "local" / "config" / "database.inc.php"
    if db_config.exists():
        content = db_config.read_text()
        replacements = [
            (r"\$conf\['db_base'\] = .*;", "$conf['db_base'] = getenv('MYSQL_DATABASE');"),
            (r"\$conf\['db_user'\] = .*;", "$conf['db_user'] = getenv('MYSQL_USERNAME');"),
            (r"\$conf\['db_password'\] = .*;", "$conf['db_password'] = getenv('MYSQL_PASSWORD');"),
            (r"\$conf\['db_host'\] = .*;", "$conf['db_host'] = getenv('MYSQL_HOST');"),
        ]
        import re

        for pattern, replacement in replacements:
            content = re.sub(pattern, replacement, content)
        db_config.write_text(content)

    # Create config.inc.php
    config_inc = DATA_DIR / "local" / "config" / "config.inc.php"
    config_inc.write_text(
        """<?php
if (!empty($_SERVER['HTTP_X_FORWARDED_FOR'])) $_SERVER['HTTP_HOST'] = $_SERVER['HTTP_X_FORWARDED_HOST'];
if ($_SERVER['HTTP_X_FORWARDED_PROTO'] == 'https') $_SERVER['HTTPS']='on';

$conf['send_bcc_mail_webmaster'] = false;
$conf['mail_allow_html'] = true;

$conf['mail_sender_name'] = getenv('MAIL_FROM_DISPLAY_NAME') ?? 'Piwigo';
$conf['mail_sender_email'] = getenv('MAIL_FROM');
$conf['smtp_host'] = getenv('SMTP_HOST') . ':' . getenv('SMTP_PORT');
$conf['smtp_user'] = getenv('SMTP_USERNAME');
$conf['smtp_password'] = getenv('SMTP_PASSWORD');
$conf['smtp_secure'] = null;
?>
"""
    )

    print("=> Piwigo initialized")


def main() -> int:
    print("=> Ensure directories and permissions")
    for d in [
        "/run/piwigo",
        "_data",
        "galleries",
        "upload",
        "plugins",
        "local/config",
        "language",
        "themes",
    ]:
        if d.startswith("/"):
            Path(d).mkdir(parents=True, exist_ok=True)
        else:
            (DATA_DIR / d).mkdir(parents=True, exist_ok=True)

    # Create php.ini if not exists
    php_ini = DATA_DIR / "php.ini"
    if not php_ini.exists():
        php_ini.write_text(
            "; Add custom PHP configuration in this file\n"
            "; Settings here are merged with the package's built-in php.ini\n\n"
        )

    config_file = DATA_DIR / "local" / "config" / "config.inc.php"
    if not config_file.exists():
        print("=> First run")
        # Run setup in background
        import threading

        t = threading.Thread(target=setup)
        t.daemon = True
        t.start()
    else:
        print("=> Sync up themes (required from 15 -> 16)")
        themes_src = CODE_DIR / "_themes"
        themes_dest = DATA_DIR / "themes"
        if themes_src.exists():
            run(["rsync", "-avc", f"{themes_src}/", f"{themes_dest}/"])

        print("=> Fixup permissions")
        run(["chown", "-R", f"{HOP3_USER}:{HOP3_USER}", str(DATA_DIR), "/run/piwigo"])

    # Run apache
    print("=> Run apache")
    pid_file = Path("/var/run/apache2/apache2.pid")
    if pid_file.exists():
        pid_file.unlink()

    os.execvp("/usr/sbin/apache2", ["/usr/sbin/apache2", "-DFOREGROUND"])


if __name__ == "__main__":
    sys.exit(main() or 0)
