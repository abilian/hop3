#!/usr/bin/env python3
"""Matomo start script for Hop3."""

import os
import shutil
import subprocess
import sys
import threading
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
MYSQL_USERNAME = os.environ.get("MYSQL_USERNAME", "matomo")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_PORT = os.environ.get("MYSQL_PORT", "3306")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "matomo")

# Mail configuration
SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
SMTP_PORT = os.environ.get("SMTP_PORT", "25")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
MAIL_FROM = os.environ.get("MAIL_FROM", "noreply@localhost")
MAIL_FROM_DISPLAY_NAME = os.environ.get("MAIL_FROM_DISPLAY_NAME", "Matomo")

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


def crudini_set(file_path: str, section: str, key: str, value: str):
    """Set a value in an INI file using crudini."""
    run(["crudini", "--set", file_path, section, key, value])


def crudini_get(file_path: str, section: str, key: str) -> str | None:
    """Get a value from an INI file using crudini."""
    result = run(
        ["crudini", "--get", file_path, section, key],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def mysql_cmd(query: str):
    """Run a MySQL query."""
    run(
        [
            "mysql",
            f"-u{MYSQL_USERNAME}",
            f"-p{MYSQL_PASSWORD}",
            f"-h{MYSQL_HOST}",
            f"-P{MYSQL_PORT}",
            f"-D{MYSQL_DATABASE}",
            "-e",
            query,
        ],
        check=False,
    )


def setup():
    """Setup Matomo after Apache starts."""
    config_file = DATA_DIR / "config" / "config.ini.php"
    console = f"php {CODE_DIR}/console"

    # Wait for Apache to start
    while not Path("/var/run/apache2/apache2.pid").exists():
        print("Waiting for apache2 to start")
        time.sleep(1)

    if not config_file.exists():
        print("=> Detected first run")

        print("=> Configuring database")
        run(
            [
                "curl",
                "--fail",
                "http://localhost:8000/index.php?action=databaseSetup&clientProtocol=https",
                "--data",
                f"type=InnoDB&host=mysql&username={MYSQL_USERNAME}&password={MYSQL_PASSWORD}"
                f"&dbname={MYSQL_DATABASE}&tables_prefix=&adapter=PDO%5CMYSQL&submit=Next+%C2%BB",
            ],
            check=False,
        )

        print("=> Creating tables")
        run(
            [
                "curl",
                "--fail",
                "-X",
                "POST",
                "http://localhost:8000/index.php?action=tablesCreation&clientProtocol=https&module=Installation",
            ],
            check=False,
        )

        print("=> Creating admin")
        run(
            [
                "curl",
                "--fail",
                "http://localhost:8000/index.php?action=setupSuperUser&clientProtocol=https&module=Installation",
                "--data",
                "login=admin&password=changeme&password_bis=changeme&email=admin%40localhost&submit=Next+%C2%BB",
            ],
            check=False,
        )

        print("=> Creating example website")
        run(
            [
                "curl",
                "--fail",
                "http://localhost:8000/index.php?action=firstWebsiteSetup&clientProtocol=https&module=Installation",
                "--data",
                "siteName=Example&url=https%3A%2F%2Fwww.example.com&timezone=UTC&ecommerce=0&submit=Next+%C2%BB",
            ],
            check=False,
        )

        print("=> Finishing installation")
        run(
            [
                "curl",
                "--fail",
                "http://localhost:8000/index.php?action=finished&clientProtocol=https&module=Installation&site_idSite=1&site_name=Example",
                "--data",
                "do_not_track=1&anonymise_ip=1&submit=Continue+to+Matomo+%C2%BB",
            ],
            check=False,
        )

        print("=> Configuring")
        cfg = str(config_file)
        crudini_set(cfg, "General", "force_ssl", "1")
        crudini_set(cfg, "General", "enable_update_communication", "0")
        crudini_set(cfg, "General", "enable_auto_update", "0")
        crudini_set(cfg, "General", "piwik_professional_support_ads_enabled", "0")
        crudini_set(cfg, "General", "cors_domains[]", "*")
        crudini_set(cfg, "General", "enable_trusted_host_check", "0")
        crudini_set(cfg, "General", "proxy_client_headers[]", "HTTP_X_FORWARDED_FOR")
        crudini_set(cfg, "General", "proxy_host_headers[]", "HTTP_X_FORWARDED_HOST")
        crudini_set(cfg, "General", "session_save_handler", "")
        crudini_set(cfg, "General", "enable_load_data_infile", "0")

        # Disable browser triggered archiving
        mysql_cmd(
            "INSERT INTO `option` (option_name, option_value) VALUES ('enableBrowserTriggerArchiving', 0);"
        )

        print("=> Run cron job to keep system check happy")
        run(["/app/scripts/cron.sh"], check=False)

        # Set geolocation provider
        mysql_cmd(
            "INSERT INTO `option` (option_name, option_value) VALUES ('usercountry.location_provider', 'geoip2php');"
        )

    print("=> Updating database settings")
    cfg = str(config_file)
    crudini_set(cfg, "database", "host", MYSQL_HOST)
    crudini_set(cfg, "database", "port", MYSQL_PORT)
    crudini_set(cfg, "database", "username", MYSQL_USERNAME)
    crudini_set(cfg, "database", "password", MYSQL_PASSWORD)
    crudini_set(cfg, "database", "dbname", MYSQL_DATABASE)

    # Get table prefix
    tables_prefix = crudini_get(cfg, "database", "tables_prefix") or ""
    if tables_prefix:
        print(f"=> table prefix:{tables_prefix}")
    else:
        print("=> no table prefix")

    print("=> Updating email settings")
    run(
        [
            "php",
            f"{CODE_DIR}/console",
            "config:set",
            "--section=mail",
            "--key=defaultHostnameIfEmpty",
            f"--value={HOP3_APP_DOMAIN}",
        ]
    )
    run(
        [
            "php",
            f"{CODE_DIR}/console",
            "config:set",
            "--section=mail",
            "--key=transport",
            "--value=smtp",
        ]
    )
    run(
        [
            "php",
            f"{CODE_DIR}/console",
            "config:set",
            "--section=mail",
            "--key=host",
            f"--value={SMTP_HOST}",
        ]
    )
    run(
        [
            "php",
            f"{CODE_DIR}/console",
            "config:set",
            "--section=mail",
            "--key=port",
            f"--value={SMTP_PORT}",
        ]
    )
    run(
        [
            "php",
            f"{CODE_DIR}/console",
            "config:set",
            "--section=mail",
            "--key=type",
            "--value=LOGIN",
        ]
    )
    run(
        [
            "php",
            f"{CODE_DIR}/console",
            "config:set",
            "--section=mail",
            "--key=username",
            f"--value={SMTP_USERNAME}",
        ]
    )
    run(
        [
            "php",
            f"{CODE_DIR}/console",
            "config:set",
            "--section=mail",
            "--key=password",
            f"--value={SMTP_PASSWORD}",
        ]
    )
    run(
        [
            "php",
            f"{CODE_DIR}/console",
            "config:set",
            "--section=mail",
            "--key=encryption",
            "--value=",
        ]
    )
    run(
        [
            "php",
            f"{CODE_DIR}/console",
            "config:set",
            "--section=General",
            "--key=noreply_email_address",
            f"--value={MAIL_FROM}",
        ]
    )
    run(
        [
            "php",
            f"{CODE_DIR}/console",
            "config:set",
            "--section=General",
            "--key=login_password_recovery_email_address",
            f"--value={MAIL_FROM}",
        ]
    )
    run(
        [
            "php",
            f"{CODE_DIR}/console",
            "config:set",
            "--section=General",
            "--key=login_password_recovery_replyto_email_address",
            f"--value={MAIL_FROM}",
        ]
    )

    if OIDC_ISSUER:
        print("=> Updating OIDC settings")
        # Remove emoji from provider name
        provider_name = run(
            [
                "php",
                "-r",
                f"echo addslashes(preg_replace('/[\\xF0-\\xF7].../s', '', \"{OIDC_PROVIDER_NAME}\"));",
            ],
            capture_output=True,
            text=True,
        ).stdout

        oidc_sql = f"""DELETE FROM `{tables_prefix}plugin_setting` WHERE `plugin_name`='LoginOIDC' and `user_login`='';
INSERT INTO `{tables_prefix}plugin_setting` (`plugin_name`, `setting_name`, `setting_value`, `user_login`) VALUES
('LoginOIDC','disableSuperuser','0', ''),
('LoginOIDC','disablePasswordConfirmation','1', ''),
('LoginOIDC','disableDirectLoginUrl','1', ''),
('LoginOIDC','allowSignup','1', ''),
('LoginOIDC','bypassTwoFa','1', ''),
('LoginOIDC','autoLinking','1', ''),
('LoginOIDC','authenticationName','Login with {provider_name}', ''),
('LoginOIDC','authorizeUrl','{OIDC_AUTH_ENDPOINT}', ''),
('LoginOIDC','tokenUrl','{OIDC_TOKEN_ENDPOINT}', ''),
('LoginOIDC','userinfoUrl','{OIDC_PROFILE_ENDPOINT}', ''),
('LoginOIDC','endSessionUrl','', ''),
('LoginOIDC','userinfoId','sub', ''),
('LoginOIDC', 'useEmailAsUsername', '0', ''),
('LoginOIDC','clientId','{OIDC_CLIENT_ID}', ''),
('LoginOIDC','clientSecret','{OIDC_CLIENT_SECRET}', ''),
('LoginOIDC','scope','openid email profile', ''),
('LoginOIDC','redirectUriOverride','', ''),
('LoginOIDC','allowedSignupDomains','', '');"""
        mysql_cmd(oidc_sql)

        print("=> Enable OIDC plugin")
        run(["php", f"{CODE_DIR}/console", "plugin:activate", "LoginOIDC"], check=False)

    print("=> Perform db migration")
    run(["php", f"{CODE_DIR}/console", "core:update", "--yes"])

    crudini_set(cfg, "General", "noreply_email_name", f'"{MAIL_FROM_DISPLAY_NAME}"')

    print("=> Ensure permissions after setup")
    run(["chown", "-R", f"{HOP3_USER}:{HOP3_USER}", "/run/matomo", str(DATA_DIR)])


def main() -> int:
    os.chdir(CODE_DIR)

    print("=> Ensure directories")
    Path("/run/matomo/tmp").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "config").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "plugins").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "misc").mkdir(parents=True, exist_ok=True)
    Path("/run/matomo/session").mkdir(parents=True, exist_ok=True)

    # Remove legacy js folder
    shutil.rmtree(DATA_DIR / "js", ignore_errors=True)

    # Copy built-in plugins
    print("=> Copy built-in plugins")
    plugins_orig = PKG_DIR / "plugins.orig"
    if plugins_orig.exists():
        for plugin_dir in plugins_orig.iterdir():
            if plugin_dir.is_dir():
                print(f"==> Copying {plugin_dir} ...")
                if OIDC_ISSUER or plugin_dir.name != "LoginOIDC":
                    dest = DATA_DIR / "plugins" / plugin_dir.name
                    if dest.exists():
                        shutil.rmtree(dest)
                    run(["rsync", "-ac", "--delete", str(plugin_dir) + "/", str(dest) + "/"])

    # Copy JS files if not exist
    piwik_js = DATA_DIR / "piwik.js"
    matomo_js = DATA_DIR / "matomo.js"
    if not piwik_js.exists():
        shutil.copy(PKG_DIR / "piwik.js.orig", piwik_js)
    if not matomo_js.exists():
        shutil.copy(PKG_DIR / "matomo.js.orig", matomo_js)

    # Create PHP config if not exists
    php_ini = DATA_DIR / "php.ini"
    if not php_ini.exists():
        php_ini.write_text(
            "; Add custom PHP configuration in this file\n"
            "; Settings here are merged with the package's built-in php.ini\n\n"
        )

    # Handle custom logo
    print("=> Handle custom logo if any")
    misc_user = DATA_DIR / "misc" / "user"
    if not misc_user.exists():
        user_orig = PKG_DIR / "user.orig"
        if user_orig.exists():
            shutil.copytree(user_orig, misc_user)

    print("=> Ensure permissions")
    run(["chown", "-R", f"{HOP3_USER}:{HOP3_USER}", "/run/matomo", str(DATA_DIR)])

    # Run setup in background
    t = threading.Thread(target=setup)
    t.daemon = True
    t.start()

    print("==> Starting matomo")
    # Source Apache envvars and start
    os.environ["APACHE_CONFDIR"] = ""
    apache_pid = Path("/var/run/apache2/apache2.pid")
    if apache_pid.exists():
        apache_pid.unlink()

    os.execvp("/usr/sbin/apache2", ["/usr/sbin/apache2", "-DFOREGROUND"])


if __name__ == "__main__":
    sys.exit(main() or 0)
