#!/usr/bin/env python3
"""Moodle start script for Hop3."""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Environment configuration
DATA_DIR = Path(os.environ.get("HOP3_DATA_DIR", "/app/data"))
CODE_DIR = Path(os.environ.get("HOP3_CODE_DIR", "/app/code"))
PKG_DIR = Path(os.environ.get("HOP3_PKG_DIR", "/app/pkg"))
HOP3_USER = os.environ.get("HOP3_USER", "www-data")

# Database configuration
POSTGRES_USERNAME = os.environ.get("POSTGRES_USERNAME", "moodle")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_DATABASE = os.environ.get("POSTGRES_DATABASE", "moodle")

# Mail configuration
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = os.environ.get("SMTP_PORT", "25")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
MAIL_FROM = os.environ.get("MAIL_FROM", "noreply@localhost")

# OIDC configuration
OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "")
OIDC_PROVIDER_NAME = os.environ.get("OIDC_PROVIDER_NAME", "SSO")
OIDC_AUTH_ENDPOINT = os.environ.get("OIDC_AUTH_ENDPOINT", "")
OIDC_TOKEN_ENDPOINT = os.environ.get("OIDC_TOKEN_ENDPOINT", "")
OIDC_PROFILE_ENDPOINT = os.environ.get("OIDC_PROFILE_ENDPOINT", "")
OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "")


def run(cmd: list[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, check=check, **kwargs)


def psql(query: str, capture: bool = False) -> str | None:
    """Run a PostgreSQL query."""
    env = {**os.environ, "PGPASSWORD": POSTGRES_PASSWORD}
    cmd = [
        "psql",
        "-h",
        POSTGRES_HOST,
        "-p",
        POSTGRES_PORT,
        "-U",
        POSTGRES_USERNAME,
        "-d",
        POSTGRES_DATABASE,
        "-AXqtc",
        query,
    ]
    if capture:
        result = run(cmd, check=False, capture_output=True, text=True, env=env)
        return result.stdout.strip() if result.returncode == 0 else ""
    run(cmd, check=False, env=env)
    return None


def psql_exec(query: str):
    """Run a PostgreSQL query with -c flag."""
    env = {**os.environ, "PGPASSWORD": POSTGRES_PASSWORD}
    run(
        [
            "psql",
            "-h",
            POSTGRES_HOST,
            "-p",
            POSTGRES_PORT,
            "-U",
            POSTGRES_USERNAME,
            "-d",
            POSTGRES_DATABASE,
            "-c",
            query,
        ],
        check=False,
        env=env,
    )


def main() -> int:
    src_dir = DATA_DIR / "moodle"
    backup_src_dir = DATA_DIR / "moodle-prev-do-not-touch"

    # Create directories
    Path("/run/moodle/sessions").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "moodledata").mkdir(parents=True, exist_ok=True)

    os.environ["PGPASSWORD"] = POSTGRES_PASSWORD

    # Create proper dirs instead of symlinks
    for subdir in ["temp", "cache", "localcache"]:
        p = DATA_DIR / "moodledata" / subdir
        if p.is_symlink() or p.exists():
            shutil.rmtree(p, ignore_errors=True)
        p.mkdir(parents=True, exist_ok=True)

    # Sessions moved to redis
    sessions_dir = DATA_DIR / "moodledata" / "sessions"
    shutil.rmtree(sessions_dir, ignore_errors=True)
    sessions_dir.mkdir(parents=True, exist_ok=True)

    # Create PHP config if not exists
    php_ini = DATA_DIR / "php.ini"
    if not php_ini.exists():
        php_ini.write_text(
            "; Add custom PHP configuration in this file\n"
            "; Settings here are merged with the package's built-in php.ini\n\n"
        )

    initialized = DATA_DIR / ".initialized"
    if not initialized.exists():
        print("==> Fresh installation, performing Moodle first time setup")
        print("==> Installing new moodle")
        run(["rsync", "-az", f"{CODE_DIR}/new/", str(src_dir)])

        # Copy config template
        shutil.copy(PKG_DIR / "templates" / "config.php.template", src_dir / "config.php")

        # Run installation
        run(
            [
                "php",
                str(src_dir / "admin" / "cli" / "install_database.php"),
                "--lang=en",
                "--adminuser=admin",
                "--adminpass=changeme123",
                "--adminemail=admin@localhost",
                "--fullname=My Moodle Site",
                "--shortname=MySite",
                "--agree-license",
            ]
        )

        initialized.touch()
        print("==> Installation done.")
    else:
        print("==> Existing installation. Will upgrade")
        print("==> Create temporary migration data")
        shutil.rmtree(backup_src_dir, ignore_errors=True)
        if src_dir.exists():
            src_dir.rename(backup_src_dir)

        print("==> Copy moodle into /app/data/moodle")
        run(["rsync", "-az", f"{CODE_DIR}/new/", str(src_dir)])

        # Copy config template
        shutil.copy(PKG_DIR / "templates" / "config.php.template", src_dir / "config.php")

        # Copy user plugins from old installation
        print("==> Copying over user plugins from old installation")
        plugintypes_php = PKG_DIR / "plugintypes.php"
        if plugintypes_php.exists():
            result = run(
                ["php", str(plugintypes_php)], capture_output=True, text=True, check=False
            )
            if result.returncode == 0:
                for subdir in result.stdout.strip().split("\n"):
                    subdir = subdir.strip()
                    if not subdir:
                        continue
                    old_plugin_dir = backup_src_dir / "public" / subdir
                    if not old_plugin_dir.exists():
                        continue

                    print(f"==> Plugin subdir {subdir}")
                    for plugin in old_plugin_dir.iterdir():
                        if not plugin.is_dir():
                            continue
                        new_plugin = src_dir / "public" / subdir / plugin.name
                        if new_plugin.exists():
                            continue
                        old_version = CODE_DIR / "old" / subdir / plugin.name
                        if old_version.exists():
                            print(
                                f"===> Skipping {plugin.name} since it is missing in newer version"
                            )
                        else:
                            print(f"===> Copying user plugin {plugin.name}")
                            shutil.copytree(plugin, new_plugin)

        print("==> Upgrading moodle")
        run(
            ["php", str(src_dir / "admin" / "cli" / "upgrade.php"), "--non-interactive"]
        )

        shutil.rmtree(backup_src_dir, ignore_errors=True)

    # SMTP Setup
    if SMTP_HOST:
        run(
            [
                "php",
                str(src_dir / "admin" / "cli" / "cfg.php"),
                "--name=smtphosts",
                f"--set={SMTP_HOST}:{SMTP_PORT}",
            ]
        )
        run(
            [
                "php",
                str(src_dir / "admin" / "cli" / "cfg.php"),
                "--name=smtpuser",
                f"--set={SMTP_USERNAME}",
            ]
        )
        run(
            [
                "php",
                str(src_dir / "admin" / "cli" / "cfg.php"),
                "--name=smtppass",
                f"--set={SMTP_PASSWORD}",
            ]
        )
        run(
            [
                "php",
                str(src_dir / "admin" / "cli" / "cfg.php"),
                "--name=noreplyaddress",
                f"--set={MAIL_FROM}",
            ]
        )

    # OIDC Configuration
    if OIDC_ISSUER:
        provider_id = psql(
            "SELECT id FROM mdl_oauth2_issuer WHERE name = 'Hop3'", capture=True
        )
        admin_id = psql("SELECT id FROM mdl_user WHERE username='admin'", capture=True) or "1"
        now = str(int(time.time()))

        if not provider_id:
            psql_exec(
                f"""INSERT INTO mdl_oauth2_issuer(name, clientid, clientsecret, baseurl, loginscopes, loginscopesoffline, showonloginpage, enabled, loginpagename, usermodified, image, loginparams, loginparamsoffline, alloweddomains, sortorder, requireconfirmation, timecreated, timemodified)
VALUES ('Hop3', '{OIDC_CLIENT_ID}', '{OIDC_CLIENT_SECRET}', '{OIDC_ISSUER}', 'openid email profile', 'openid email profile', 1, 1, '{OIDC_PROVIDER_NAME}', {admin_id}, '', '', '', '', 1, 0, {now}, {now})"""
            )
            provider_id = psql(
                "SELECT id FROM mdl_oauth2_issuer WHERE name = 'Hop3'", capture=True
            )
        else:
            psql_exec(
                f"""UPDATE mdl_oauth2_issuer SET clientid='{OIDC_CLIENT_ID}', clientsecret='{OIDC_CLIENT_SECRET}', baseurl='{OIDC_ISSUER}', loginpagename='{OIDC_PROVIDER_NAME}' WHERE id={provider_id}"""
            )

        if provider_id:
            psql_exec(f"DELETE FROM mdl_oauth2_endpoint WHERE issuerid={provider_id}")
            psql_exec(
                f"INSERT INTO mdl_oauth2_endpoint (issuerid, name, url, usermodified, timecreated, timemodified) VALUES ({provider_id}, 'authorization_endpoint', '{OIDC_AUTH_ENDPOINT}', {admin_id}, {now}, {now})"
            )
            psql_exec(
                f"INSERT INTO mdl_oauth2_endpoint (issuerid, name, url, usermodified, timecreated, timemodified) VALUES ({provider_id}, 'token_endpoint', '{OIDC_TOKEN_ENDPOINT}', {admin_id}, {now}, {now})"
            )
            psql_exec(
                f"INSERT INTO mdl_oauth2_endpoint (issuerid, name, url, usermodified, timecreated, timemodified) VALUES ({provider_id}, 'userinfo_endpoint', '{OIDC_PROFILE_ENDPOINT}', {admin_id}, {now}, {now})"
            )

            psql_exec(
                f"DELETE FROM mdl_oauth2_user_field_mapping WHERE issuerid={provider_id}"
            )
            psql_exec(
                f"INSERT INTO mdl_oauth2_user_field_mapping (issuerid, externalfield, internalfield, usermodified, timecreated, timemodified) VALUES ({provider_id}, 'email', 'email', {admin_id}, {now}, {now})"
            )
            psql_exec(
                f"INSERT INTO mdl_oauth2_user_field_mapping (issuerid, externalfield, internalfield, usermodified, timecreated, timemodified) VALUES ({provider_id}, 'given_name', 'firstname', {admin_id}, {now}, {now})"
            )
            psql_exec(
                f"INSERT INTO mdl_oauth2_user_field_mapping (issuerid, externalfield, internalfield, usermodified, timecreated, timemodified) VALUES ({provider_id}, 'family_name', 'lastname', {admin_id}, {now}, {now})"
            )

        # Enable oauth2 plugin
        run(
            [
                "php",
                str(src_dir / "admin" / "cli" / "cfg.php"),
                "--name=auth",
                "--set=oauth2",
            ]
        )

    print("==> Fixing permissions")
    run(["chown", "-R", f"{HOP3_USER}:{HOP3_USER}", "/run/moodle", str(DATA_DIR)])
    # Make config.php owned by root for security
    config_php = DATA_DIR / "moodle" / "config.php"
    if config_php.exists():
        run(["chown", "root:root", str(config_php)], check=False)

    # Start Apache
    os.environ["APACHE_CONFDIR"] = ""
    apache_pid = Path("/var/run/apache2/apache2.pid")
    if apache_pid.exists():
        apache_pid.unlink()

    os.execvp("/usr/sbin/apache2", ["/usr/sbin/apache2", "-DFOREGROUND"])


if __name__ == "__main__":
    sys.exit(main() or 0)
