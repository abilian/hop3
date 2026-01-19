# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Nginx configuration."""

from __future__ import annotations

import grp
import os
import pwd
import subprocess
from pathlib import Path

from hop3_installer.common import (
    CommandError,
    print_detail,
    print_error,
    print_info,
    print_success,
    print_warning,
    run_cmd,
)

from .config import (
    HOME_DIR,
    HOP3_GROUP,
    HOP3_USER,
    NGINX_CONFIG,
    SSL_CERT,
    SSL_KEY,
    SUDOERS_CONTENT,
    ServerInstallerConfig,
)


def setup_nginx(config: ServerInstallerConfig) -> None:
    """Configure nginx as reverse proxy."""
    if config.skip_nginx:
        print_info("Skipping nginx setup (--skip-nginx)")
        return

    # Determine server name
    server_name = config.domain if config.domain else "_"

    # Generate nginx config
    nginx_config = NGINX_CONFIG.format(
        server_name=server_name,
        ssl_cert=str(SSL_CERT),
        ssl_key=str(SSL_KEY),
    )

    # Write config file
    nginx_config_path = Path("/etc/nginx/sites-available/hop3")
    nginx_enabled_path: Path | None = Path("/etc/nginx/sites-enabled/hop3")

    # For Fedora/RHEL, use conf.d instead
    if not Path("/etc/nginx/sites-available").exists():
        nginx_config_path = Path("/etc/nginx/conf.d/hop3.conf")
        nginx_enabled_path = None

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

    # Test nginx config
    try:
        run_cmd(["nginx", "-t"])
        print_success("Nginx configuration is valid")
    except CommandError as e:
        print_error(f"Nginx configuration test failed: {e.stderr[:200]}")
        return

    # Configure sudoers
    setup_sudoers()

    # Enable and start nginx
    run_cmd(["systemctl", "enable", "nginx"], check=False)
    result = run_cmd(["systemctl", "restart", "nginx"], check=False)
    if result.returncode != 0:
        print_warning("Failed to restart nginx")
        print_detail("Check status with: journalctl -u nginx -n 50")
        print_detail("Check config with: nginx -t")
    else:
        print_success("Nginx enabled and started")


def _add_hop3_nginx_include() -> None:
    """Add include directive for hop3 app configs to nginx.conf."""
    nginx_conf = Path("/etc/nginx/nginx.conf")
    include_line = "include /home/hop3/nginx/*.conf;"

    if not nginx_conf.exists():
        print_warning("nginx.conf not found, skipping app include setup")
        return

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

    if include_added:
        nginx_conf.write_text("\n".join(new_lines))
        print_success("Added hop3 app nginx include to nginx.conf")
    else:
        print_warning("Could not find suitable location for nginx include")


def setup_sudoers() -> None:
    """Configure sudo permissions for hop3 user."""
    sudoers_file = Path("/etc/sudoers.d/hop3")

    try:
        sudoers_file.write_text(SUDOERS_CONTENT)
        Path(sudoers_file).chmod(0o440)

        # Validate with visudo
        result = subprocess.run(
            ["visudo", "-c", "-f", str(sudoers_file)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print_warning(f"Invalid sudoers file: {result.stderr}")
            sudoers_file.unlink()
            return

        print_success("Sudoers configured for hop3 service management")
    except Exception as e:
        print_warning(f"Could not configure sudoers: {e}")
