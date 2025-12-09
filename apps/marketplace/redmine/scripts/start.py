#!/usr/bin/env python3
"""Redmine start script for Hop3."""

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

# App configuration
HOP3_APP_DOMAIN = os.environ.get("HOP3_APP_DOMAIN", "localhost")

# Database configuration
MYSQL_USERNAME = os.environ.get("MYSQL_USERNAME", "redmine")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_PORT = os.environ.get("MYSQL_PORT", "3306")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "redmine")

# Mail configuration
SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
SMTP_PORT = os.environ.get("SMTP_PORT", "25")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
MAIL_FROM = os.environ.get("MAIL_FROM", "noreply@localhost")
MAIL_FROM_DISPLAY_NAME = os.environ.get("MAIL_FROM_DISPLAY_NAME", "")
MAIL_DOMAIN = os.environ.get("MAIL_DOMAIN", "localhost")

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


def mysql_cmd(query: str):
    """Run a MySQL query."""
    run(
        [
            "mysql",
            "--defaults-file=/run/redmine/mysql-extra",
            f"--user={MYSQL_USERNAME}",
            f"--host={MYSQL_HOST}",
            "-P",
            MYSQL_PORT,
            MYSQL_DATABASE,
            "-e",
            query,
        ],
        check=False,
    )


def yq_set(file_path: str, key: str, value: str):
    """Set a value in a YAML file using yq."""
    run(["yq", "eval", "-i", f"{key}={value}", file_path])


def main() -> int:
    print("=> Ensure directories")
    for subdir in ["files", "assets", "plugin_assets", "themes", "redmine_extensions", ".ssh"]:
        (DATA_DIR / subdir).mkdir(parents=True, exist_ok=True)

    for subdir in ["log", "tmp/pdf", "vendor", "dotbundle"]:
        Path(f"/run/redmine/{subdir}").mkdir(parents=True, exist_ok=True)

    # Remove stale pid file
    pid_file = CODE_DIR / "tmp" / "pids" / "server.pid"
    if pid_file.exists():
        pid_file.unlink()

    # Create MySQL credentials file
    Path("/run/redmine/mysql-extra").write_text(f"[client]\npassword={MYSQL_PASSWORD}\n")

    os.environ["HOME"] = "/tmp"

    # Copy plugins on first run
    plugins_dir = DATA_DIR / "plugins"
    if not plugins_dir.exists():
        shutil.copytree(CODE_DIR / "plugins.orig", plugins_dir)

    # Setup files
    shutil.copy(CODE_DIR / "Gemfile.lock.save", "/run/redmine/Gemfile.lock")
    Path("/run/redmine/schema.rb").touch()
    (DATA_DIR / "additional_environment.rb").touch()

    # Setup symlinks
    symlinks = [
        ("/run/redmine/dotbundle", CODE_DIR / ".bundle"),
        ("/run/redmine/vendor", CODE_DIR / "vendor"),
        ("/run/redmine/database.yml", CODE_DIR / "config" / "database.yml"),
        ("/run/redmine/configuration.yml", CODE_DIR / "config" / "configuration.yml"),
        (DATA_DIR / "secrets.yml", CODE_DIR / "config" / "secrets.yml"),
        (DATA_DIR / "files", CODE_DIR / "files"),
        (DATA_DIR / "assets", CODE_DIR / "public" / "assets"),
        (DATA_DIR / "plugin_assets", CODE_DIR / "public" / "plugin_assets"),
        (DATA_DIR / "themes", CODE_DIR / "themes"),
        (DATA_DIR / "plugins", CODE_DIR / "plugins"),
        ("/run/redmine/tmp", CODE_DIR / "tmp"),
        ("/run/redmine/log", CODE_DIR / "log"),
        ("/run/redmine/Gemfile.lock", CODE_DIR / "Gemfile.lock"),
        ("/run/redmine/schema.rb", CODE_DIR / "db" / "schema.rb"),
        (DATA_DIR / ".ssh", Path(f"/home/{HOP3_USER}/.ssh")),
        (DATA_DIR / "additional_environment.rb", CODE_DIR / "config" / "additional_environment.rb"),
    ]

    for target, link in symlinks:
        link = Path(link)
        link.parent.mkdir(parents=True, exist_ok=True)
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(target)

    # Copy ImageMagick policy
    policy_src = PKG_DIR / "conf" / "policy.xml"
    if policy_src.exists():
        shutil.copy(policy_src, "/etc/ImageMagick-6/policy.xml")

    # Copy production.rb
    shutil.copy(
        PKG_DIR / "conf" / "production.rb",
        CODE_DIR / "config" / "environments" / "production.rb",
    )

    print("=> Generate database config")
    shutil.copy(PKG_DIR / "templates" / "database.yml.template", "/run/redmine/database.yml")
    db_yml = "/run/redmine/database.yml"
    yq_set(db_yml, f'.production.database', f'"{MYSQL_DATABASE}"')
    yq_set(db_yml, f'.production.host', f'"{MYSQL_HOST}"')
    yq_set(db_yml, f'.production.port', f'"{MYSQL_PORT}"')
    yq_set(db_yml, f'.production.username', f'"{MYSQL_USERNAME}"')
    yq_set(db_yml, f'.production.password', f'"{MYSQL_PASSWORD}"')

    print("=> Generate email config")
    shutil.copy(
        PKG_DIR / "templates" / "configuration.yml.template",
        "/run/redmine/configuration.yml",
    )
    conf_yml = "/run/redmine/configuration.yml"
    yq_set(conf_yml, '.default.email_delivery.smtp_settings.address', f'"{SMTP_HOST}"')
    yq_set(conf_yml, '.default.email_delivery.smtp_settings.port', SMTP_PORT)
    yq_set(conf_yml, '.default.email_delivery.smtp_settings.domain', f'"{MAIL_DOMAIN}"')
    yq_set(conf_yml, '.default.email_delivery.smtp_settings.user_name', f'"{SMTP_USERNAME}"')
    yq_set(conf_yml, '.default.email_delivery.smtp_settings.password', f'"{SMTP_PASSWORD}"')

    print("=> Fixing /tmp permissions")
    os.chmod("/tmp", 0o1777)

    print("=> Installing plugin gems")
    bundle_orig = CODE_DIR / ".bundle.orig"
    if bundle_orig.exists():
        for item in bundle_orig.iterdir():
            dest = Path("/run/redmine/dotbundle") / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy(item, dest)

    vendor_done = Path("/run/redmine/vendor/.done")
    if not vendor_done.exists():
        print("=> Copying redmine vendor gems on first run")
        vendor_orig = CODE_DIR / "vendor.orig"
        if vendor_orig.exists():
            for item in vendor_orig.iterdir():
                dest = Path("/run/redmine/vendor") / item.name
                if item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                else:
                    shutil.copy(item, dest)
        print("=> Installing gems of plugins")
        run(["bundle", "install"], cwd=CODE_DIR)

    vendor_done.touch()

    run(["chown", "-R", f"{HOP3_USER}:{HOP3_USER}", str(DATA_DIR), "/run/redmine"])

    secrets_yml = DATA_DIR / "secrets.yml"
    if not secrets_yml.exists():
        print("=> First run")
        print("=> Generate session secret")
        result = run(
            ["bundle", "exec", "rails", "secret"],
            capture_output=True,
            text=True,
            cwd=CODE_DIR,
        )
        secret = result.stdout.strip()
        secrets_yml.write_text(f"production:\n  secret_key_base: {secret}\n")

        os.environ["SECRET_KEY_BASE"] = secret

        print("=> Run database migration")
        run(
            [
                "su",
                "-s",
                "/bin/bash",
                HOP3_USER,
                "-c",
                f"cd {CODE_DIR} && bundle exec rake db:migrate",
            ]
        )

        print("=> Setup default data")
        run(
            [
                "su",
                "-s",
                "/bin/bash",
                HOP3_USER,
                "-c",
                f"cd {CODE_DIR} && bundle exec rake redmine:load_default_data",
            ]
        )

        # Disable registration with OIDC
        if OIDC_ISSUER:
            mysql_cmd(
                "INSERT INTO settings (name, value, updated_on) VALUES ('self_registration', 0, NOW())"
            )
    else:
        print("=> Run database migration")
        # Extract secret from secrets.yml
        content = secrets_yml.read_text()
        for line in content.split("\n"):
            if "secret_key_base:" in line:
                secret = line.split("secret_key_base:")[1].strip()
                os.environ["SECRET_KEY_BASE"] = secret
                break

        run(
            [
                "su",
                "-s",
                "/bin/bash",
                HOP3_USER,
                "-c",
                f"cd {CODE_DIR} && bundle exec rake db:migrate",
            ],
            cwd=CODE_DIR,
        )

    print("=> Ensure mail from address")
    mail_from = MAIL_FROM
    if MAIL_FROM_DISPLAY_NAME:
        mail_from = f"{MAIL_FROM_DISPLAY_NAME} <{MAIL_FROM}>"
    mail_from_base64 = base64.b64encode(mail_from.encode()).decode()
    mysql_cmd(
        f"INSERT INTO settings (name, value) VALUES ('mail_from', FROM_BASE64('{mail_from_base64}')) ON DUPLICATE KEY UPDATE name='mail_from', value=FROM_BASE64('{mail_from_base64}');"
    )

    print("=> Set hostname")
    mysql_cmd(
        f"INSERT INTO settings (name, value) VALUES ('host_name', '{HOP3_APP_DOMAIN}') ON DUPLICATE KEY UPDATE name='host_name', value='{HOP3_APP_DOMAIN}';"
    )
    mysql_cmd(
        "INSERT INTO settings (name, value) VALUES ('protocol', 'https') ON DUPLICATE KEY UPDATE name='protocol', value='https';"
    )

    if OIDC_ISSUER:
        print("=> Update OIDC config")
        # Update OIDC plugin files
        oidc_plugin_dest = DATA_DIR / "plugins" / "redmine_oauth"
        shutil.rmtree(oidc_plugin_dest, ignore_errors=True)
        shutil.copytree(CODE_DIR / "plugins.orig" / "redmine_oauth", oidc_plugin_dest)

        # Clean provider name
        provider_name = run(
            [
                "php",
                "-r",
                f"echo addslashes(preg_replace('/[\\xf0-\\xf7].../s', '', \"{OIDC_PROVIDER_NAME}\"));",
            ],
            capture_output=True,
            text=True,
        ).stdout

        mysql_cmd("DELETE FROM settings WHERE name='plugin_redmine_oauth';")

        plugin_value = f"""--- !ruby/hash:ActiveSupport::HashWithIndifferentAccess
oauth_name: Custom
button_color: "#ffbe6f"
button_icon: fas fa-address-card
site: ''
client_id: {OIDC_CLIENT_ID}
client_secret: {OIDC_CLIENT_SECRET}
tenant_id: ''
custom_name: "{provider_name}"
custom_auth_endpoint: {OIDC_AUTH_ENDPOINT}
custom_token_endpoint: {OIDC_TOKEN_ENDPOINT}
custom_profile_endpoint: {OIDC_PROFILE_ENDPOINT}
custom_scope: openid profile email
custom_uid_field: sub
custom_email_field: email
self_registration: "3"
"""
        # Escape for SQL
        plugin_value_escaped = plugin_value.replace("'", "''")
        mysql_cmd(
            f"INSERT INTO settings (name, value, updated_on) VALUES ('plugin_redmine_oauth', '{plugin_value_escaped}', NOW())"
        )

    print("=> Migrate plugins")
    run(
        [
            "su",
            "-s",
            "/bin/bash",
            HOP3_USER,
            "-c",
            f"cd {CODE_DIR} && bundle exec rake redmine:plugins:migrate",
        ],
        cwd=CODE_DIR,
    )

    print("=> Precompile assets")
    run(
        [
            "su",
            "-s",
            "/bin/bash",
            HOP3_USER,
            "-c",
            f"cd {CODE_DIR} && bundle exec rake assets:precompile",
        ],
        cwd=CODE_DIR,
    )

    print("==> Starting redmine")
    os.execvp(
        "su",
        [
            "su",
            "-s",
            "/bin/bash",
            HOP3_USER,
            "-c",
            f"cd {CODE_DIR} && bundle exec rails server -u webrick -e production -b 0.0.0.0",
        ],
    )


if __name__ == "__main__":
    sys.exit(main() or 0)
