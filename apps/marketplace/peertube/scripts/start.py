#!/usr/bin/env python3
"""PeerTube start script for Hop3."""

import os
import secrets
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

# App configuration
HOP3_APP_DOMAIN = os.environ.get("HOP3_APP_DOMAIN", "localhost")

# Database configuration
POSTGRES_USERNAME = os.environ.get("POSTGRES_USERNAME", "peertube")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_DATABASE = os.environ.get("POSTGRES_DATABASE", "peertube")

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
OIDC_PROVIDER_NAME = os.environ.get("OIDC_PROVIDER_NAME", "SSO")
OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "")

# PeerTube plugin version
PEERTUBE_OPENID_PLUGIN_VERSION = os.environ.get("PEERTUBE_OPENID_PLUGIN_VERSION", "1.0.3")


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


def yq_set(file_path: str, key: str, value: str):
    """Set a value in a YAML file using yq."""
    run(["yq", "eval", f"{key} = {value}", "-i", file_path])


def yq_get(file_path: str, key: str) -> str:
    """Get a value from a YAML file using yq."""
    result = run(
        ["yq", "eval", key, file_path], capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


def yq_del(file_path: str, key: str):
    """Delete a key from a YAML file using yq."""
    run(["yq", "eval", f"del({key})", "-i", file_path])


def install_oidc():
    """Install OIDC plugin."""
    if OIDC_ISSUER:
        print("==> Installing OIDC plugin")
        run(
            [
                "npm",
                "run",
                "plugin:install",
                "--",
                "-n",
                "peertube-plugin-auth-openid-connect",
                "-v",
                PEERTUBE_OPENID_PLUGIN_VERSION,
            ],
            cwd=CODE_DIR / "server",
            check=False,
        )
        update_oidc()


def update_oidc():
    """Update OIDC configuration in database."""
    print("==> Updating OIDC config")
    provider_name = OIDC_PROVIDER_NAME.replace("'", "''")
    discovery_url = OIDC_DISCOVERY_URL or f"{OIDC_ISSUER}/.well-known/openid-configuration"

    settings = {
        "scope": "openid email profile",
        "client-id": OIDC_CLIENT_ID,
        "discover-url": discovery_url,
        "client-secret": OIDC_CLIENT_SECRET,
        "mail-property": "email",
        "auth-display-name": provider_name,
        "username-property": "preferred_username",
        "signature-algorithm": "RS256",
        "display-name-property": "name",
    }

    import json

    settings_json = json.dumps(settings).replace("'", "''")
    psql(
        f"UPDATE plugin SET settings='{settings_json}' WHERE name='auth-openid-connect'"
    )


def first_time_setup():
    """Run first time setup after starting PeerTube."""
    print("==> Starting peertube to run migrations on first run")
    proc = subprocess.Popen(["npm", "start"], cwd=CODE_DIR / "server")
    time.sleep(10)

    # Wait for PeerTube to be ready
    while True:
        result = run(
            ["curl", "--silent", "--output", "/dev/null", "--fail", "http://localhost:9000/"],
            check=False,
        )
        if result.returncode == 0:
            break
        print("==> Waiting for peertube")
        time.sleep(5)

    # Kill the process
    run(["killall", "-SIGTERM", "peertube"], check=False)
    time.sleep(5)

    print("==> Reset root password")
    run(
        ["npm", "run", "reset-password", "--", "-u", "root"],
        input="changeme\n",
        text=True,
        cwd=CODE_DIR / "server",
        check=False,
    )
    time.sleep(5)

    install_oidc()
    print("==> First time setup complete")


def update_config():
    """Update PeerTube configuration."""
    print("==> Ensure and updating configs")
    config_file = str(DATA_DIR / "production.yaml")

    # Generate secret if needed
    if yq_get(config_file, ".secrets.peertube") == "":
        secret = secrets.token_hex(32)
        yq_set(config_file, ".secrets.peertube", f'"{secret}"')

    yq_set(config_file, ".webserver.hostname", f'"{HOP3_APP_DOMAIN}"')

    # Database configuration
    yq_set(config_file, ".database.hostname", f'"{POSTGRES_HOST}"')
    yq_set(config_file, ".database.port", POSTGRES_PORT)
    yq_set(config_file, ".database.username", f'"{POSTGRES_USERNAME}"')
    yq_set(config_file, ".database.password", f'"{POSTGRES_PASSWORD}"')
    yq_set(config_file, ".database.name", f'"{POSTGRES_DATABASE}"')
    yq_del(config_file, ".database.suffix")

    # Redis configuration
    yq_set(config_file, ".redis.hostname", f'"{REDIS_HOST}"')
    yq_set(config_file, ".redis.port", REDIS_PORT)
    yq_set(config_file, ".redis.auth", f'"{REDIS_PASSWORD}"')

    # SMTP configuration
    yq_set(config_file, ".smtp.hostname", f'"{SMTP_HOST}"')
    yq_set(config_file, ".smtp.port", SMTP_PORT)
    yq_set(config_file, ".smtp.username", f'"{SMTP_USERNAME}"')
    yq_set(config_file, ".smtp.password", f'"{SMTP_PASSWORD}"')
    yq_set(config_file, ".smtp.tls", "false")
    yq_set(config_file, ".smtp.disable_starttls", "true")
    yq_set(config_file, ".smtp.from_address", f'"{MAIL_FROM}"')

    # Storage paths
    storage_paths = [
        ("bin", "bin"),
        ("well_known", "well_known"),
        ("tmp_persistent", "tmp_persistent"),
        ("well_known", "well-known"),
        ("uploads", "uploads"),
        ("client_overrides", "client-overrides"),
        ("storyboards", "storyboards"),
        ("original_video_files", "original_video_files"),
    ]

    for key, folder in storage_paths:
        yq_set(config_file, f".storage.{key}", f'"{DATA_DIR}/storage/{folder}/"')

    # Check for private files setting
    if yq_get(config_file, ".static_files.private_files_require_auth") == "":
        yq_set(config_file, ".static_files.private_files_require_auth", "true")

    # Migrate videos to web-videos
    videos_dir = DATA_DIR / "storage" / "videos"
    web_videos_dir = DATA_DIR / "storage" / "web-videos"
    if videos_dir.exists():
        print("==> Migrate videos/ to web-videos/")
        videos_dir.rename(web_videos_dir)

    yq_set(config_file, ".storage.web_videos", f'"{DATA_DIR}/storage/web-videos/"')
    yq_del(config_file, ".storage.videos")
    yq_del(config_file, ".transcoding.webtorrent")
    yq_set(config_file, ".transcoding.web_videos.enabled", "true")


def main() -> int:
    # Create directories
    (DATA_DIR / "storage").mkdir(parents=True, exist_ok=True)
    Path("/run/peertube/cache").mkdir(parents=True, exist_ok=True)
    Path("/run/peertube/npm").mkdir(parents=True, exist_ok=True)
    Path("/tmp/peertube").mkdir(parents=True, exist_ok=True)

    os.chdir(CODE_DIR / "server")

    print("==> Changing ownership")
    run(
        [
            "chown",
            "-R",
            f"{HOP3_USER}:{HOP3_USER}",
            str(DATA_DIR),
            "/run/peertube",
            "/tmp/peertube",
        ]
    )

    # Wait for Redis and set eviction policy
    redis_env = {"REDISCLI_AUTH": REDIS_PASSWORD}
    while True:
        result = run(
            ["redis-cli", "-h", REDIS_HOST, "-p", REDIS_PORT, "ping"],
            check=False,
            capture_output=True,
            env={**os.environ, **redis_env},
        )
        if result.returncode == 0:
            break
        print("==> Waiting for redis")
        time.sleep(5)

    run(
        [
            "redis-cli",
            "-h",
            REDIS_HOST,
            "-p",
            REDIS_PORT,
            "CONFIG",
            "SET",
            "maxmemory-policy",
            "noeviction",
        ],
        env={**os.environ, **redis_env},
    )

    production_yaml = DATA_DIR / "production.yaml"
    if not production_yaml.exists():
        print("==> First run. creating config")
        shutil.copy(PKG_DIR / "templates" / "production.yaml.template", production_yaml)
        update_config()
        first_time_setup()
    else:
        update_config()
        if OIDC_ISSUER:
            install_oidc()
            update_oidc()

    print("==> Configuring nginx")
    shutil.copy(PKG_DIR / "conf" / "nginx.conf", "/run/peertube-nginx.conf")

    print("==> Starting PeerTube")
    os.execvp(
        "/usr/bin/supervisord",
        [
            "/usr/bin/supervisord",
            "--configuration",
            "/etc/supervisor/supervisord.conf",
            "--nodaemon",
            "-i",
            "PeerTube",
        ],
    )


if __name__ == "__main__":
    sys.exit(main() or 0)
