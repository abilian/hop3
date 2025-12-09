#!/usr/bin/env python3
"""OpenProject start script for Hop3."""

import os
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
POSTGRES_USERNAME = os.environ.get("POSTGRES_USERNAME", "openproject")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_DATABASE = os.environ.get("POSTGRES_DATABASE", "openproject")

# Mail configuration
SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
SMTP_PORT = os.environ.get("SMTP_PORT", "25")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
MAIL_FROM = os.environ.get("MAIL_FROM", "noreply@localhost")
MAIL_DOMAIN = os.environ.get("MAIL_DOMAIN", "localhost")

# LDAP configuration
LDAP_URL = os.environ.get("LDAP_URL", "")
LDAP_HOST = os.environ.get("LDAP_HOST", "localhost")
LDAP_PORT = os.environ.get("LDAP_PORT", "389")
LDAP_BIND_DN = os.environ.get("LDAP_BIND_DN", "")
LDAP_BIND_PASSWORD = os.environ.get("LDAP_BIND_PASSWORD", "")
LDAP_USERS_BASE_DN = os.environ.get("LDAP_USERS_BASE_DN", "")


def run(cmd: list[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, check=check, **kwargs)


def psql(query: str):
    """Run a PostgreSQL query."""
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
    os.chdir(CODE_DIR)

    is_update = (DATA_DIR / "files").exists()

    # Create directories
    Path("/run/openproject/tmp").mkdir(parents=True, exist_ok=True)
    Path("/tmp/log").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "repositories").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "files").mkdir(parents=True, exist_ok=True)

    os.environ["HOME"] = "/run"
    os.environ["TMPDIR"] = "/run/openproject/tmp"

    # Setup symlinks
    symlinks = [
        ("/run/database.yml", CODE_DIR / "config" / "database.yml"),
        ("/run/secrets.yml", CODE_DIR / "config" / "secrets.yml"),
        ("/run/openproject/tmp", CODE_DIR / "tmp"),
        ("/tmp/log", CODE_DIR / "log"),
        (DATA_DIR / "schema.rb", CODE_DIR / "db" / "schema.rb"),
        (DATA_DIR / "repositories", CODE_DIR / "repositories"),
        (DATA_DIR / "files", CODE_DIR / "files"),
        ("/run/openproject/supervisord.log", Path("/var/log/supervisor/supervisord.log")),
    ]

    for target, link in symlinks:
        link = Path(link)
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(target)

    print("=> Setup database configuration")
    db_template = (PKG_DIR / "templates" / "database.yml.template").read_text()
    db_config = (
        db_template.replace("##POSTGRESQL_HOST##", POSTGRES_HOST)
        .replace("##POSTGRESQL_PORT##", POSTGRES_PORT)
        .replace("##POSTGRESQL_USERNAME##", POSTGRES_USERNAME)
        .replace("##POSTGRESQL_PASSWORD##", POSTGRES_PASSWORD)
        .replace("##POSTGRESQL_DATABASE##", POSTGRES_DATABASE)
    )
    Path("/run/database.yml").write_text(db_config)

    # Source custom overrides
    env_file = DATA_DIR / "env.sh"
    if not env_file.exists():
        env_file.write_text(
            '# Override env variables \n\n#export OPENPROJECT_LOG__LEVEL="info"\n'
        )

    # Source env.sh
    env_content = env_file.read_text()
    for line in env_content.strip().split("\n"):
        if line.startswith("export "):
            kv = line[7:]
            if "=" in kv:
                key, _, value = kv.partition("=")
                value = value.strip('"').strip("'")
                os.environ[key] = value

    # Set environment variables
    os.environ["ADMIN_EMAIL"] = MAIL_FROM
    os.environ["OPENPROJECT_EMAIL__DELIVERY__METHOD"] = "smtp"
    os.environ["OPENPROJECT_SMTP__ADDRESS"] = SMTP_HOST
    os.environ["OPENPROJECT_SMTP__PORT"] = SMTP_PORT
    os.environ["OPENPROJECT_SMTP__DOMAIN"] = MAIL_DOMAIN
    os.environ["OPENPROJECT_SMTP__AUTHENTICATION"] = "plain"
    os.environ["OPENPROJECT_SMTP__USER__NAME"] = SMTP_USERNAME
    os.environ["OPENPROJECT_SMTP__PASSWORD"] = SMTP_PASSWORD
    os.environ["OPENPROJECT_SMTP__ENABLE__STARTTLS__AUTO"] = "true"
    os.environ["OPENPROJECT_HOST__NAME"] = HOP3_APP_DOMAIN
    os.environ["PGPASSWORD"] = POSTGRES_PASSWORD

    print("=> Setting cookie secret")
    secret_result = run(
        ["./bin/rails", "secret"], capture_output=True, text=True, cwd=CODE_DIR
    )
    secret_key_base = secret_result.stdout.strip()
    os.environ["SECRET_KEY_BASE"] = secret_key_base

    # Create secrets.yml
    secrets_template = (PKG_DIR / "templates" / "secrets.yml.template").read_text()
    secrets_config = secrets_template.replace("##SECRET_KEY_BASE##", secret_key_base)
    Path("/run/secrets.yml").write_text(secrets_config)

    print("=> Migrate database")
    run(["./bin/rake", "db:migrate"], cwd=CODE_DIR)

    print("=> Seed database if needed")
    # Disable email delivery during seeding
    os.environ["OPENPROJECT_EMAIL_DELIVERY_METHOD"] = ""
    run(["./bin/rake", "db:seed"], check=False, cwd=CODE_DIR)
    os.environ["OPENPROJECT_EMAIL_DELIVERY_METHOD"] = "smtp"

    # LDAP configuration
    if LDAP_URL:
        print("=> Update LDAP config")
        ldap_query = f"""
INSERT INTO ldap_auth_sources (id, name, host, port, account, account_password, base_dn, attr_login, attr_firstname, attr_lastname, attr_mail, onthefly_register, tls_mode, created_at, updated_at)
VALUES (1, 'Hop3', '{LDAP_HOST}', {LDAP_PORT}, '{LDAP_BIND_DN}', '{LDAP_BIND_PASSWORD}', '{LDAP_USERS_BASE_DN}', 'username', 'givenName', 'sn', 'mail', TRUE, 0, NOW(), NOW())
ON CONFLICT (id) DO UPDATE
SET name='Hop3', host='{LDAP_HOST}', port={LDAP_PORT}, account='{LDAP_BIND_DN}', account_password='{LDAP_BIND_PASSWORD}', base_dn='{LDAP_USERS_BASE_DN}', attr_login='username', attr_firstname='givenName', attr_lastname='sn', attr_mail='mail', onthefly_register=TRUE, tls_mode=0, updated_at=NOW();
"""
        psql(ldap_query)

        # Disable self registration and password reset for LDAP
        psql("UPDATE settings SET value=0 WHERE name='self_registration';")
        psql("UPDATE settings SET value=0 WHERE name='lost_password';")

    print("=> Update general config")
    settings = [
        ("protocol", "https"),
        ("password_min_length", "8"),
        ("email_delivery_method", "smtp"),
        ("smtp_address", SMTP_HOST),
        ("smtp_port", SMTP_PORT),
        ("smtp_domain", MAIL_DOMAIN),
        ("smtp_authentication", "plain"),
        ("smtp_user_name", SMTP_USERNAME),
        ("smtp_password", SMTP_PASSWORD),
        ("smtp_enable_starttls_auto", "0"),
        ("mail_from", MAIL_FROM),
        ("host_name", HOP3_APP_DOMAIN),
        ("email_login", "1"),
    ]

    for name, value in settings:
        psql(f"UPDATE settings SET value='{value}' WHERE name='{name}';")

    print("=> Clear previous cache to reflect db changes")
    run(["./bin/rake", "tmp:clear"], cwd=CODE_DIR)

    print("=> Fixup the directory permissions")
    run(
        ["chown", "-R", f"{HOP3_USER}:{HOP3_USER}", str(DATA_DIR), "/run", "/tmp"]
    )

    print("=> Starting supervisor")
    os.execvp(
        "/usr/bin/supervisord",
        [
            "/usr/bin/supervisord",
            "--configuration",
            "/etc/supervisor/supervisord.conf",
            "--nodaemon",
            "-i",
            "OpenProject",
        ],
    )


if __name__ == "__main__":
    sys.exit(main() or 0)
