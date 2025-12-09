#!/usr/bin/env python3
"""DokuWiki start script for Hop3."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Environment configuration
DATA_DIR = Path(os.environ.get("HOP3_DATA_DIR", "/app/data"))
CODE_DIR = Path(os.environ.get("HOP3_CODE_DIR", "/app/code"))
PKG_DIR = Path(os.environ.get("HOP3_PKG_DIR", "/app/pkg"))

# OIDC configuration
OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "")
OIDC_PROVIDER_NAME = os.environ.get("OIDC_PROVIDER_NAME", "SSO")
MAIL_FROM_DISPLAY_NAME = os.environ.get("MAIL_FROM_DISPLAY_NAME", "DokuWiki")


def run(cmd: list[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, check=check, **kwargs)


def main() -> int:
    # Initialize data directory on first run
    data_data = DATA_DIR / "data"
    if not data_data.exists():
        print("==> Initializing data directory on first run")
        shutil.copytree(CODE_DIR / "data", data_data)
    else:
        # rsync equivalent - sync with ignore-existing and exclude patterns
        run(
            [
                "rsync",
                "-v",
                "-a",
                "--ignore-existing",
                "--exclude",
                "pages/*",
                "--exclude",
                "log/",
                f"{CODE_DIR}/data/",
                f"{DATA_DIR}/data/",
            ]
        )

    # Create necessary directories
    for d in ["conf", "templates", "plugins"]:
        (DATA_DIR / d).mkdir(parents=True, exist_ok=True)
    Path("/run/dokuwiki/sessions").mkdir(parents=True, exist_ok=True)
    Path("/run/dokuwiki/log").mkdir(parents=True, exist_ok=True)

    # Setup log symlink
    log_path = DATA_DIR / "data" / "log"
    if log_path.exists() or log_path.is_symlink():
        if log_path.is_dir() and not log_path.is_symlink():
            shutil.rmtree(log_path)
        else:
            log_path.unlink()
    log_path.symlink_to("/run/dokuwiki/log")

    # Copy conf files
    conf_orig = CODE_DIR / "conf.orig"
    if conf_orig.exists():
        for f in conf_orig.glob("*.php"):
            shutil.copy(f, DATA_DIR / "conf" / f.name)
        for f in conf_orig.glob("*.conf"):
            shutil.copy(f, DATA_DIR / "conf" / f.name)
        htaccess = conf_orig / ".htaccess"
        if htaccess.exists():
            shutil.copy(htaccess, DATA_DIR / "conf" / ".htaccess")

    # Copy preload.php if needed (for siteexport plugin)
    preload_dest = DATA_DIR / "preload.php"
    if not preload_dest.exists():
        preload_src = CODE_DIR / "inc" / "preload.php.dist"
        if preload_src.exists():
            shutil.copy(preload_src, preload_dest)

    # Copy templates
    tpl_orig = CODE_DIR / "lib" / "tpl.orig"
    if tpl_orig.exists():
        for f in tpl_orig.iterdir():
            dest = DATA_DIR / "templates" / f.name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(f, dest)

    # Copy plugins (except auth plugins)
    plugins_orig = CODE_DIR / "lib" / "plugins.orig"
    if plugins_orig.exists():
        for f in plugins_orig.iterdir():
            # Skip auth plugins
            if f.is_dir() and f.name.startswith("auth"):
                continue
            print(f"==> Copying plugin: {f.name}")
            dest = DATA_DIR / "plugins" / f.name
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            if f.is_dir():
                shutil.copytree(f, dest)
            else:
                shutil.copy(f, dest)

    # Set environment defaults
    if not MAIL_FROM_DISPLAY_NAME:
        os.environ["MAIL_FROM_DISPLAY_NAME"] = "DokuWiki"
    if not OIDC_PROVIDER_NAME:
        os.environ["OIDC_PROVIDER_NAME"] = "SSO"

    # Copy protected config template
    shutil.copy(
        PKG_DIR / "templates" / "local.protected.php.template",
        DATA_DIR / "conf" / "local.protected.php",
    )

    # Create ACL file if needed
    acl_file = DATA_DIR / "conf" / "acl.auth.php"
    if not acl_file.exists():
        acl_template = CODE_DIR / "conf.orig" / "acl.auth.php.template"
        if acl_template.exists():
            shutil.copy(acl_template, acl_file)

    local_php = DATA_DIR / "conf" / "local.php"

    if OIDC_ISSUER:
        print("==> Setting up OIDC")

        # Copy auth plugins
        for plugin in ["authplain", "oauth", "oauthgeneric"]:
            src = plugins_orig / plugin
            if src.exists():
                dest = DATA_DIR / "plugins" / plugin
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(src, dest)

        # Add plugin configuration
        plugins_required = DATA_DIR / "conf" / "plugins.required.php"
        if plugins_required.exists():
            content = plugins_required.read_text()
        else:
            content = "<?php\n"

        if "plugins['oauth'] = 1" not in content:
            content += "\n$plugins['oauth'] = 1;\n$plugins['oauthgeneric'] = 1;\n"
            plugins_required.write_text(content)

        # Create users file if needed
        users_file = DATA_DIR / "conf" / "users.auth.php"
        if not users_file.exists():
            users_template = CODE_DIR / "conf.orig" / "users.auth.php.dist"
            if users_template.exists():
                shutil.copy(users_template, users_file)

        # Create local.php if needed
        if not local_php.exists():
            local_php.write_text(
                """<?php

// Add custom configuration here
// make users as doku wiki admins (https://www.dokuwiki.org/config:superuser)
// $conf['superuser']   = 'username';
"""
            )

        # Disable open registration
        content = local_php.read_text()
        if "openregister" not in content:
            content += "\n$conf['openregister'] = 0;\n"
            local_php.write_text(content)
    else:
        print("==> Setting up plain auth")

        # Copy authplain plugin
        src = plugins_orig / "authplain"
        if src.exists():
            dest = DATA_DIR / "plugins" / "authplain"
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)

        # Create users file if needed
        users_file = DATA_DIR / "conf" / "users.auth.php"
        if not users_file.exists():
            users_template = CODE_DIR / "conf.orig" / "users.auth.php.dist"
            if users_template.exists():
                shutil.copy(users_template, users_file)

        # Create local.php if needed
        if not local_php.exists():
            local_php.write_text(
                """<?php

// Add custom configuration here
// $conf['title'] = 'My Wiki';
"""
            )

    # Create php.ini if needed
    php_ini = DATA_DIR / "php.ini"
    if not php_ini.exists():
        php_ini.write_text(
            "; Add custom PHP configuration in this file\n"
            "; Settings here are merged with the package's built-in php.ini\n\n"
        )

    # Change ownership
    run(["chown", "-R", "www-data:www-data", str(DATA_DIR), "/run/dokuwiki"])

    # Start apache
    print("==> Starting apache")
    # Source apache envvars
    run(["bash", "-c", "APACHE_CONFDIR='' source /etc/apache2/envvars"])

    # Remove PID file if exists
    pid_file = Path("/var/run/apache2/apache2.pid")
    if pid_file.exists():
        pid_file.unlink()

    os.execvp("/usr/sbin/apache2", ["/usr/sbin/apache2", "-DFOREGROUND"])


if __name__ == "__main__":
    sys.exit(main() or 0)
