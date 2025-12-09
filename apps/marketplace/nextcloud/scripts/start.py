#!/usr/bin/env python3
"""Nextcloud start script for Hop3."""

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

# App configuration
HOP3_APP_ORIGIN = os.environ.get("HOP3_APP_ORIGIN", "http://localhost")
HOP3_APP_DOMAIN = os.environ.get("HOP3_APP_DOMAIN", "localhost")
HOP3_PROXY_IP = os.environ.get("HOP3_PROXY_IP", "")

# Database configuration
POSTGRES_USERNAME = os.environ.get("POSTGRES_USERNAME", "nextcloud")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_DATABASE = os.environ.get("POSTGRES_DATABASE", "nextcloud")

# Redis configuration
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = os.environ.get("REDIS_PORT", "6379")
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "")

# Mail configuration
SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
SMTP_PORT = os.environ.get("SMTP_PORT", "25")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
MAIL_FROM = os.environ.get("MAIL_FROM", "noreply@localhost")

# OIDC configuration
OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "")
OIDC_DISCOVERY_URL = os.environ.get("OIDC_DISCOVERY_URL", "")
OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "")

# TURN configuration
TURN_SERVER = os.environ.get("TURN_SERVER", "")
TURN_PORT = os.environ.get("TURN_PORT", "")
TURN_SECRET = os.environ.get("TURN_SECRET", "")
STUN_SERVER = os.environ.get("STUN_SERVER", "")
STUN_PORT = os.environ.get("STUN_PORT", "")


def run(cmd: list[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, check=check, **kwargs)


def occ(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run Nextcloud occ command."""
    return run(["php", f"{CODE_DIR}/occ"] + args, check=check)


def main() -> int:
    # Parse mail from
    mail_parts = MAIL_FROM.split("@")
    mail_from_sub = mail_parts[0] if len(mail_parts) > 0 else "noreply"
    mail_domain_sub = mail_parts[1] if len(mail_parts) > 1 else "localhost"

    Path("/run/nextcloud/sessions").mkdir(parents=True, exist_ok=True)

    # Check if first run
    if not any(DATA_DIR.iterdir()) if DATA_DIR.exists() else True:
        print("==> Detected first run")
        (DATA_DIR / "config").mkdir(parents=True, exist_ok=True)
        shutil.copytree(PKG_DIR / "apps_template", DATA_DIR / "apps")
        shutil.copy(PKG_DIR / "htaccess.template", DATA_DIR / "htaccess")

        print("==> Install nextcloud")
        run(
            [
                "php",
                f"{CODE_DIR}/occ",
                "maintenance:install",
                "--database",
                "pgsql",
                "--database-name",
                POSTGRES_DATABASE,
                "--database-user",
                POSTGRES_USERNAME,
                "--database-pass",
                POSTGRES_PASSWORD,
                "--database-host",
                POSTGRES_HOST,
                "--database-port",
                POSTGRES_PORT,
                "--admin-user",
                "admin",
                "--admin-pass",
                "changeme",
                "--data-dir",
                str(DATA_DIR / "data"),
                "-n",
            ]
        )
    else:
        new_apps = PKG_DIR / "apps_template"
        old_apps = DATA_DIR / "apps"

        print("==> Updating apps")
        print("==> Old apps:")
        if new_apps.exists():
            for app in new_apps.iterdir():
                print(f"  {app.name}")
        if old_apps.exists():
            for app in old_apps.iterdir():
                print(f"  {app.name}")

        if new_apps.exists():
            for app in new_apps.iterdir():
                if app.is_dir():
                    print(f"==> Update app: {app.name}")
                    dest = old_apps / app.name
                    shutil.rmtree(dest, ignore_errors=True)
                    shutil.copytree(app, dest)

        print("==> New apps:")
        if new_apps.exists():
            for app in new_apps.iterdir():
                print(f"  {app.name}")
        if old_apps.exists():
            for app in old_apps.iterdir():
                print(f"  {app.name}")

        print("==> Copying htaccess")
        shutil.copy(PKG_DIR / "htaccess.template", DATA_DIR / "htaccess")

    # Ensure symlink for scss files
    core_link = DATA_DIR / "core"
    if core_link.is_symlink() or core_link.exists():
        core_link.unlink()
    core_link.symlink_to(CODE_DIR / "core")

    run(
        [
            "chown",
            "-R",
            f"{HOP3_USER}:{HOP3_USER}",
            str(DATA_DIR / "config"),
            str(DATA_DIR / "apps"),
            str(DATA_DIR / "htaccess"),
        ]
    )
    run(["chown", f"{HOP3_USER}:{HOP3_USER}", str(DATA_DIR)])
    if (DATA_DIR / "data").exists():
        run(["chown", f"{HOP3_USER}:{HOP3_USER}", str(DATA_DIR / "data")])

    print("==> update config")
    config_content = f"""<?php
$CONFIG = array (
    'trusted_domains' => array ( 0 => '{HOP3_APP_DOMAIN}' ),
    'trusted_proxies' => array ( 0 => '{HOP3_PROXY_IP}' ),
    'forcessl' => true,
    'mail_smtpmode' => 'smtp',
    'mail_smtpauth' => 1,
    'mail_sendmailmode' => 'smtp',
    'mail_smtpauthtype' => 'LOGIN',
    'mail_smtphost' => '{SMTP_HOST}',
    'mail_smtpport' => '{SMTP_PORT}',
    'mail_smtpname' => '{SMTP_USERNAME}',
    'mail_smtppassword' => '{SMTP_PASSWORD}',
    'mail_from_address' => '{mail_from_sub}',
    'mail_smtpsecure' => '',
    'mail_domain' => '{mail_domain_sub}',
    'maintenance_window_start' => 1,
    'overwrite.cli.url' => '{HOP3_APP_ORIGIN}/',
    'overwritehost' => '{HOP3_APP_DOMAIN}',
    'overwriteprotocol' => 'https',
    'log_type' => 'file',
    'logfile' => '/run/nextcloud/nextcloud.log',
    'loglevel' => 3,
    'dbtype' => 'pgsql',
    'dbname' => '{POSTGRES_DATABASE}',
    'dbuser' => '{POSTGRES_USERNAME}',
    'dbpassword' => '{POSTGRES_PASSWORD}',
    'dbhost' => '{POSTGRES_HOST}',
    'dbtableprefix' => 'oc_',
    'updatechecker' => false,
    'redis' => array(
        'host' => '{REDIS_HOST}',
        'port' => {REDIS_PORT},
        'password' => '{REDIS_PASSWORD}'
    ),
    'memcache.local' => '\\OC\\Memcache\\Redis',
    'memcache.locking' => '\\OC\\Memcache\\Redis',
    'integrity.check.disabled' => true,
    'localstorage.allowsymlinks' => true,
    'htaccess.RewriteBase' => '/',
    'simpleSignUpLink.shown' => false,
    'dns_pinning' => false
);
"""
    (DATA_DIR / "config" / "hop3.config.php").write_text(config_content)

    # Create PHP config if not exists
    php_ini = DATA_DIR / "php.ini"
    if not php_ini.exists():
        php_ini.write_text(
            "; Add custom PHP configuration in this file\n"
            "; Settings here are merged with the package's built-in php.ini\n\n"
        )

    # Apache config
    (DATA_DIR / "apache").mkdir(parents=True, exist_ok=True)
    mpm_conf = DATA_DIR / "apache" / "mpm_prefork.conf"
    if not mpm_conf.exists():
        shutil.copy(PKG_DIR / "mpm_prefork.conf", mpm_conf)

    print("==> turning off maintenance mode")
    occ(["maintenance:mode", "--off"], check=False)

    print("==> running upgrade")
    occ(["upgrade"], check=False)
    occ(["db:convert-filecache-bigint", "--no-interaction"], check=False)
    occ(["maintenance:update:htaccess"], check=False)
    occ(["maintenance:repair", "--include-expensive"], check=False)

    # Patch htaccess for caldav/carddav
    htaccess_file = DATA_DIR / "htaccess"
    if htaccess_file.exists():
        content = htaccess_file.read_text()
        content = re.sub(r"caldav /", "caldav https://%{HTTP_HOST}/", content)
        content = re.sub(r"carddav /", "carddav https://%{HTTP_HOST}/", content)
        htaccess_file.write_text(content)

    # Add missing database indices
    occ(["db:add-missing-indices"], check=False)
    occ(["db:add-missing-columns"], check=False)
    occ(["db:add-missing-primary-keys"], check=False)

    print("==> Changing ownership")
    run(["chown", "-R", f"{HOP3_USER}:{HOP3_USER}", "/run/nextcloud"])

    # OIDC configuration
    if OIDC_ISSUER:
        print("==> Ensure OIDC settings")
        occ(["app:install", "user_oidc"], check=False)

        discovery_url = OIDC_DISCOVERY_URL or f"{OIDC_ISSUER}/.well-known/openid-configuration"
        occ(
            [
                "user_oidc:provider",
                "Hop3",
                f"--clientid={OIDC_CLIENT_ID}",
                f"--clientsecret={OIDC_CLIENT_SECRET}",
                f"--discoveryuri={discovery_url}",
                "--scope=openid email profile groups",
                "--mapping-groups=groups",
                "--unique-uid=0",
                "--mapping-uid=sub",
            ],
            check=False,
        )

    # TURN configuration
    if TURN_SERVER:
        print("==> Installing and enabling spreed, if needed")
        occ(["app:install", "spreed"], check=False)
        occ(["app:enable", "spreed"], check=False)

        occ(
            [
                "config:app:set",
                "spreed",
                "stun_servers",
                "--value",
                f'["{STUN_SERVER}:{STUN_PORT}"]',
            ]
        )
        occ(
            [
                "config:app:set",
                "spreed",
                "turn_servers",
                "--value",
                f'[{{"server":"{TURN_SERVER}:{TURN_PORT}","secret":"{TURN_SECRET}","protocols":"udp,tcp"}}]',
            ]
        )

    # Run cron job on startup
    print("==> Run cron job on startup")
    run(["php", "-f", f"{CODE_DIR}/cron.php"], check=False)

    print("==> Start NextCloud")
    os.execvp(
        "/usr/bin/supervisord",
        [
            "/usr/bin/supervisord",
            "--configuration",
            "/etc/supervisor/supervisord.conf",
            "--nodaemon",
            "-i",
            "NextCloud",
        ],
    )


if __name__ == "__main__":
    sys.exit(main() or 0)
