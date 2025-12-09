#!/usr/bin/env python3
"""Rocket.Chat start script for Hop3."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Environment configuration
DATA_DIR = Path(os.environ.get("HOP3_DATA_DIR", "/app/data"))
CODE_DIR = Path(os.environ.get("HOP3_CODE_DIR", "/app/code"))
HOP3_USER = os.environ.get("HOP3_USER", "www-data")

# App configuration
HOP3_APP_ORIGIN = os.environ.get("HOP3_APP_ORIGIN", "http://localhost:3000")

# MongoDB configuration
MONGODB_HOST = os.environ.get("MONGODB_HOST", "localhost")
MONGODB_PORT = os.environ.get("MONGODB_PORT", "27017")
MONGODB_DATABASE = os.environ.get("MONGODB_DATABASE", "rocketchat")
MONGODB_USERNAME = os.environ.get("MONGODB_USERNAME", "rocketchat")
MONGODB_PASSWORD = os.environ.get("MONGODB_PASSWORD", "")
MONGODB_URL = os.environ.get("MONGODB_URL", "")
MONGODB_OPLOG_URL = os.environ.get("MONGODB_OPLOG_URL", "")

# Mail configuration
SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
SMTP_PORT = os.environ.get("SMTP_PORT", "25")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
MAIL_FROM = os.environ.get("MAIL_FROM", "noreply@localhost")
MAIL_FROM_DISPLAY_NAME = os.environ.get("MAIL_FROM_DISPLAY_NAME", "")

# TURN configuration
STUN_SERVER = os.environ.get("STUN_SERVER", "")
STUN_PORT = os.environ.get("STUN_PORT", "3478")
TURN_SERVER = os.environ.get("TURN_SERVER", "")
TURN_PORT = os.environ.get("TURN_PORT", "3478")
TURN_SECRET = os.environ.get("TURN_SECRET", "")

# OIDC configuration
OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "")
OIDC_PROVIDER_NAME = os.environ.get("OIDC_PROVIDER_NAME", "SSO")
OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "")


def run(cmd: list[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, check=check, **kwargs)


def mongosh(eval_cmd: str):
    """Run a MongoDB shell command."""
    mongo_cli = [
        "mongosh",
        "--quiet",
        f"{MONGODB_HOST}:{MONGODB_PORT}/{MONGODB_DATABASE}",
        "-u",
        MONGODB_USERNAME,
        "-p",
        MONGODB_PASSWORD,
        "--eval",
        eval_cmd,
    ]
    run(mongo_cli, check=False)


def update_setting(setting_id: str, value: str | bool | dict):
    """Update a Rocket.Chat setting in MongoDB."""
    if isinstance(value, bool):
        value_str = "true" if value else "false"
    elif isinstance(value, dict):
        value_str = json.dumps(value).replace('"', '\\"')
        mongosh(
            f'db.rocketchat_settings.updateOne({{ _id: "{setting_id}" }}, {{ $set: {{ value: {value_str} }}}}, {{ upsert: true }})'
        )
        return
    else:
        value_str = f'"{value}"'

    mongosh(
        f'db.rocketchat_settings.updateOne({{ _id: "{setting_id}" }}, {{ $set: {{ value: {value_str} }}}}, {{ upsert: true }})'
    )


def main() -> int:
    print("=> Creating runtime directories")
    Path("/run/rocket.chat/babel-cache").mkdir(parents=True, exist_ok=True)
    Path("/run/rocket.chat/ufs").mkdir(parents=True, exist_ok=True)
    Path("/run/rocket.chat/deno-cache").mkdir(parents=True, exist_ok=True)
    Path("/run/root.mongodb/mongosh").mkdir(parents=True, exist_ok=True)

    # Setup babel cache symlink
    babel_cache_link = Path(f"/home/{HOP3_USER}/.babel-cache")
    if babel_cache_link.is_symlink() or babel_cache_link.exists():
        babel_cache_link.unlink()
    try:
        babel_cache_link.symlink_to("/run/rocket.chat/babel-cache")
    except OSError:
        pass

    # Migrate old env file
    old_env = DATA_DIR / "env"
    new_env = DATA_DIR / "env.sh"
    if old_env.exists():
        old_env.rename(new_env)

    if not new_env.exists():
        print("=> First run setup")
        new_env.write_text(
            "# Add custom env configuration in this file\n\n# export CREATE_TOKENS_FOR_USERS=true\n"
        )
        mongosh(
            'db.rocketchat_settings.updateOne({ _id: "Accounts_TwoFactorAuthentication_By_Email_Auto_Opt_In" }, { $set: { value: false }}, { upsert: true })'
        )

    if OIDC_ISSUER:
        print("Setting up OIDC")
        provider_name = OIDC_PROVIDER_NAME.replace("\\", "\\\\").replace('"', '\\"')

        # OIDC settings
        oidc_settings = [
            ("Accounts_OAuth_Custom-Hop3", True, {"group": "OAuth", "section": "Custom OAuth: Hop3", "type": "boolean"}),
            ("Accounts_OAuth_Custom-Hop3-url", OIDC_ISSUER, {"type": "string"}),
            ("Accounts_OAuth_Custom-Hop3-id", OIDC_CLIENT_ID, {"type": "string"}),
            ("Accounts_OAuth_Custom-Hop3-secret", OIDC_CLIENT_SECRET, {"type": "string"}),
            ("Accounts_OAuth_Custom-Hop3-token_path", "/token", {"type": "string"}),
            ("Accounts_OAuth_Custom-Hop3-authorize_path", "/auth", {"type": "string"}),
            ("Accounts_OAuth_Custom-Hop3-scope", "openid email profile", {"type": "string"}),
            ("Accounts_OAuth_Custom-Hop3-identity_path", "/me", {"type": "string"}),
            ("Accounts_OAuth_Custom-Hop3-username_field", "sub", {"type": "string"}),
            ("Accounts_OAuth_Custom-Hop3-email_field", "email", {"type": "string"}),
            ("Accounts_OAuth_Custom-Hop3-name_field", "name", {"type": "string"}),
            ("Accounts_OAuth_Custom-Hop3-login_style", "redirect", {"type": "select"}),
            ("Accounts_OAuth_Custom-Hop3-button_label_text", f"Login with {provider_name}", {"type": "string"}),
            ("Accounts_OAuth_Custom-Hop3-button_color", "#1d74f5", {"type": "string"}),
            ("Accounts_OAuth_Custom-Hop3-show_button", True, {"type": "boolean"}),
            ("Accounts_OAuth_Custom-Hop3-token_sent_via", "payload", {"type": "select"}),
            ("Accounts_OAuth_Custom-Hop3-identity_token_sent_via", "header", {"type": "select"}),
            ("Accounts_OAuth_Custom-Hop3-access_token_param", "access_token", {"type": "string"}),
            ("Accounts_OAuth_Custom-Hop3-key_field", "username", {"type": "select"}),
        ]

        for setting_id, value, meta in oidc_settings:
            if isinstance(value, bool):
                val_str = "true" if value else "false"
            else:
                val_str = f'"{value}"'

            mongosh(
                f'db.rocketchat_settings.updateOne({{ _id: "{setting_id}"}}, {{ $set: {{ value: {val_str}, group: "OAuth", section: "Custom OAuth: Hop3" }}}}, {{ upsert: true }})'
            )

    # Update site URL
    print("=> Update site url")
    update_setting("Site_Url", HOP3_APP_ORIGIN)

    # Email settings
    print("=> Setting up email")
    update_setting("SMTP_Host", SMTP_HOST)
    update_setting("SMTP_Port", SMTP_PORT)
    update_setting("SMTP_Username", SMTP_USERNAME)
    update_setting("SMTP_Password", SMTP_PASSWORD)

    # From email
    if MAIL_FROM_DISPLAY_NAME:
        from_email = f"{MAIL_FROM_DISPLAY_NAME} <{MAIL_FROM}>"
    else:
        from_email = MAIL_FROM

    os.environ["from_email"] = from_email
    mongosh(
        f'db.rocketchat_settings.updateOne({{ _id: "From_Email" }}, {{ $set: {{ value: "{from_email}" }}}}, {{ upsert: true }})'
    )

    # TURN configuration
    if STUN_SERVER:
        webrtc_value = f"stun:{STUN_SERVER}:{STUN_PORT}, :{TURN_SECRET}@turn:{TURN_SERVER}:{TURN_PORT}"
        update_setting("WebRTC_Servers", webrtc_value)

    # Disable update checker
    mongosh(
        'db.rocketchat_settings.updateOne({ _id: "Update_EnableChecker" }, { $set: { value: false }}, { upsert: true })'
    )

    run(["chown", "-R", f"{HOP3_USER}:{HOP3_USER}", str(DATA_DIR), "/run/rocket.chat"])

    # Source env.sh
    env_content = new_env.read_text()
    for line in env_content.strip().split("\n"):
        if line.startswith("export "):
            kv = line[7:]
            if "=" in kv:
                key, _, value = kv.partition("=")
                value = value.strip('"').strip("'")
                os.environ[key] = value

    # Set environment variables
    os.environ["ROOT_URL"] = HOP3_APP_ORIGIN
    mongo_url = (
        MONGODB_URL
        or f"mongodb://{MONGODB_USERNAME}:{MONGODB_PASSWORD}@{MONGODB_HOST}:{MONGODB_PORT}/{MONGODB_DATABASE}"
    )
    os.environ["MONGO_URL"] = mongo_url
    os.environ["MONGO_OPLOG_URL"] = MONGODB_OPLOG_URL
    os.environ["PORT"] = "3000"
    os.environ["DENO_DIR"] = "/run/rocket.chat/deno-cache"
    os.environ["SKIP_MONGODEPRECATION_CHECK"] = "true"

    print("=> Starting Rocket.Chat")
    os.execvp(
        "su",
        [
            "su",
            "-s",
            "/bin/bash",
            HOP3_USER,
            "-c",
            f"cd {CODE_DIR} && node {CODE_DIR}/bundle/main.js",
        ],
    )


if __name__ == "__main__":
    sys.exit(main() or 0)
