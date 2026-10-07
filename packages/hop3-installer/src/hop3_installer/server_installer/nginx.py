# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Nginx configuration."""

from __future__ import annotations

import grp
import os
import pwd
from pathlib import Path

from hop3_installer.common import (
    InstallStepError,
    has_systemd,
    print_info,
    print_success,
    process_manager_pending,
    run_cmd,
)
from hop3_installer.constants import (
    HOME_DIR,
    HOP3_GROUP,
    HOP3_USER,
    SYSTEM_SSL_CERT,
    SYSTEM_SSL_KEY,
)
from hop3_installer.nginx_templates import generate_full_ssl_config

from .config import ServerInstallerConfig


def _disable_conflicting_webservers() -> None:
    """
    Disable Apache and other webservers that conflict with Nginx.

    Apache is often installed as a dependency of PHP packages (libapache2-mod-php).
    We need to stop and disable it to prevent port 80/443 conflicts with Nginx.
    """
    # List of services to disable (covers both Debian and RHEL naming)
    conflicting_services = ["apache2", "httpd"]

    for service in conflicting_services:
        # Check if service exists
        result = run_cmd(
            ["systemctl", "list-unit-files", f"{service}.service"], check=False
        )
        if result.returncode != 0 or service not in result.stdout:
            continue

        # Stop the service
        result = run_cmd(["systemctl", "stop", service], check=False)
        if result.returncode == 0:
            print_info(f"Stopped {service}")

        # Disable the service from starting on boot
        result = run_cmd(["systemctl", "disable", service], check=False)
        if result.returncode == 0:
            print_info(f"Disabled {service}")

        # Mask the service to prevent accidental re-enabling
        result = run_cmd(["systemctl", "mask", service], check=False)
        if result.returncode == 0:
            print_success(f"Masked {service} to prevent conflicts with Nginx")


#: Hop3's own `http`-level nginx settings. conf.d is included inside `http`
#: by the stock nginx.conf of every distribution Hop3 installs on.
NGINX_HTTP_SETTINGS_PATH = Path("/etc/nginx/conf.d/hop3-http.conf")

#: Every app vhost's names go into one hash, whose bucket must hold the longest
#: name. nginx's default (64 on most builds) refuses a long but legal hostname:
#: `hop3-tuto-nix-gen-flask.135.181.203.156.sslip.io` failed `nginx -t` with
#: "could not build server_names_hash", and so did the deploy. 256 holds the
#: longest name DNS allows (253 characters).
NGINX_HTTP_SETTINGS = """\
# Written by the Hop3 installer.
server_names_hash_bucket_size 256;
"""


def setup_nginx(config: ServerInstallerConfig) -> None:
    """Configure nginx as reverse proxy."""
    if config.skip_nginx:
        # A redeploy skips the site config (admin domain, certificates), but
        # the http settings are the platform's and follow it on every install:
        # gated here, they reached only fresh installs.
        _reconcile_http_settings()
        print_info("Skipping nginx site setup (--skip-nginx)")
        return

    # Disable conflicting webservers (Apache) before configuring Nginx
    _disable_conflicting_webservers()

    # Determine server name
    server_name = config.domain or "_"

    # Determine config path. Debian/Ubuntu: sites-available + sites-enabled
    # symlink. Fedora/RHEL: conf.d (no sites-enabled).
    nginx_config_path = Path("/etc/nginx/sites-available/hop3")
    nginx_enabled_path: Path | None = Path("/etc/nginx/sites-enabled/hop3")
    if not Path("/etc/nginx/sites-available").exists():
        nginx_config_path = Path("/etc/nginx/conf.d/hop3.conf")
        nginx_enabled_path = None

    # Claim nginx's default_server so the bare host / any unmatched Host reaches
    # the Hop3 control plane, not whichever app vhost nginx parsed first. Only
    # safe on the sites-enabled (Debian) path, where we remove the distro's
    # `default` site below; on RHEL/conf.d the stock nginx.conf already ships a
    # `listen 80 default_server`, and a second one fails `nginx -t`. There we
    # rely on an explicit server_name match instead.
    use_default_server = nginx_enabled_path is not None

    # Generate nginx config
    nginx_config = generate_full_ssl_config(
        server_name=server_name,
        ssl_cert=str(SYSTEM_SSL_CERT),
        ssl_key=str(SYSTEM_SSL_KEY),
        default_server=use_default_server,
    )

    nginx_config_path.parent.mkdir(parents=True, exist_ok=True)
    nginx_config_path.write_text(nginx_config)
    print_success(f"Nginx config written to {nginx_config_path}")

    # Create symlink if using sites-available/sites-enabled
    if nginx_enabled_path:
        nginx_enabled_path.parent.mkdir(parents=True, exist_ok=True)
        if nginx_enabled_path.exists() or nginx_enabled_path.is_symlink():
            nginx_enabled_path.unlink()
        nginx_enabled_path.symlink_to(nginx_config_path)
        print_success("Nginx site enabled")

        # Remove default site if exists
        default_site = Path("/etc/nginx/sites-enabled/default")
        if default_site.exists() or default_site.is_symlink():
            default_site.unlink()
            print_info("Removed default nginx site")

    # Add include for app-specific configs
    _add_hop3_nginx_include()
    _write_http_settings()

    # Test nginx config: it raises with nginx's own diagnosis.
    run_cmd(["nginx", "-t"])
    print_success("Nginx configuration is valid")

    # Enable and start nginx — but only where systemd is what runs it.
    #
    # Not a fallback to the init script, deliberately: on a non-systemd target
    # the process manager owns nginx (`[program:nginx]` in the supervisor
    # config), and a second nginx started here would fight it for :80. So say
    # who has it instead. This previously printed "Failed to restart nginx" with
    # advice to read `journalctl` — on a box with neither systemd nor a journal,
    # for a step that was never this installer's to do.
    if not has_systemd():
        print_info("systemd not detected; the process manager will start nginx")
        return

    run_cmd(["systemctl", "enable", "nginx"])
    run_cmd(["systemctl", "restart", "nginx"])
    print_success("Nginx enabled and started")


def _write_http_settings() -> bool:
    """Write :data:`NGINX_HTTP_SETTINGS` if they differ; True when written."""
    if (
        NGINX_HTTP_SETTINGS_PATH.exists()
        and NGINX_HTTP_SETTINGS_PATH.read_text() == NGINX_HTTP_SETTINGS
    ):
        return False
    NGINX_HTTP_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    NGINX_HTTP_SETTINGS_PATH.write_text(NGINX_HTTP_SETTINGS)
    print_success(f"Nginx http settings written to {NGINX_HTTP_SETTINGS_PATH}")
    return True


def _reconcile_http_settings() -> None:
    """
    Bring a running nginx's http settings up to date.

    Validated before the reload, so a rejected setting stops the install with
    nginx's own message instead of being signalled to a master that ignores
    it. `nginx -s reload` signals the master through its pid file, whichever
    process manager started it.
    """
    if not _write_http_settings():
        print_info("Nginx http settings already up to date")
        return
    run_cmd(["nginx", "-t"])
    if process_manager_pending():
        print_info("nginx will load these settings when the process manager starts it")
        return
    run_cmd(["nginx", "-s", "reload"])
    print_success("Nginx reloaded with the new http settings")


def _add_hop3_nginx_include() -> None:
    """Add include directive for hop3 app configs to nginx.conf."""
    nginx_conf = Path("/etc/nginx/nginx.conf")
    include_line = "include /home/hop3/nginx/*.conf;"

    # Without the include, nginx ignores every app vhost the server writes.
    if not nginx_conf.exists():
        msg = f"{nginx_conf} not found: nginx cannot be told to load the apps' configs"
        raise InstallStepError(msg)

    content = nginx_conf.read_text()

    if include_line in content:
        print_info("Hop3 app nginx include already configured")
        return

    # Create the nginx directory for app configs
    hop3_nginx_dir = HOME_DIR / "nginx"
    hop3_nginx_dir.mkdir(parents=True, exist_ok=True)
    hop3_uid = pwd.getpwnam(HOP3_USER).pw_uid
    hop3_gid = grp.getgrnam(HOP3_GROUP).gr_gid
    os.chown(hop3_nginx_dir, hop3_uid, hop3_gid)

    # Find the right place to add the include
    lines = content.split("\n")
    new_lines = []
    include_added = False

    for line in lines:
        new_lines.append(line)
        if not include_added and "include" in line:
            if "sites-enabled" in line or "conf.d" in line:
                indent = len(line) - len(line.lstrip())
                new_lines.append(" " * indent + include_line)
                include_added = True

    if not include_added:
        msg = (
            f"{nginx_conf} has no `include` of sites-enabled or conf.d to put "
            f"`{include_line}` beside: this nginx layout is not one the "
            f"installer knows, so the apps' configs would never be loaded"
        )
        raise InstallStepError(msg)
    nginx_conf.write_text("\n".join(new_lines))
    print_success("Added hop3 app nginx include to nginx.conf")
