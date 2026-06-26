# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Nginx configuration templates for hop3-installer.

This module centralizes all nginx configuration templates used by both
the server installer and the deployer to ensure consistency and eliminate
duplication (DRY principle).

Templates use double braces {{ }} for nginx variables that should be
preserved in the output, and single braces { } for Python string formatting.
"""

from __future__ import annotations

import re

from hop3_installer.constants import ACME_WEBROOT, HOP3_SERVER_BIND

# Validate every server_name before it reaches a template — catches
# typos and any future input source whose trust posture might change.
# See notes/security.md §3.5 / §1.2 for the boundary argument. The
# literal ``_`` is allowed as nginx's default-server wildcard.
_DOMAIN_NAME_RE: re.Pattern[str] = re.compile(
    r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}$"
)


def _validate_server_name(server_name: str) -> str:
    """Return ``server_name`` unchanged or raise ValueError on bad shape."""
    if server_name == "_":
        return server_name
    if not server_name or len(server_name) > 253:
        msg = (
            f"Invalid server_name {server_name!r}: must be a 1-253 char "
            "RFC 1035 domain or the wildcard '_'."
        )
        raise ValueError(msg)
    if not _DOMAIN_NAME_RE.fullmatch(server_name):
        msg = (
            f"Invalid server_name {server_name!r}: must match RFC 1035 "
            "domain shape (letters/digits/hyphens, dots between labels) "
            "or be the wildcard '_'."
        )
        raise ValueError(msg)
    return server_name


def is_fqdn(value: str) -> bool:
    """True if ``value`` is a usable RFC-1035 domain (not an IP, not ``_``).

    Used to decide whether a deploy host can double as the admin domain — an
    IPv4 address fails (the TLD must be ≥2 letters) and so does ``localhost``
    (no dot), so neither is mistaken for a servable hostname.
    """
    return bool(_DOMAIN_NAME_RE.fullmatch(value))


def _default_server_suffix(default_server: bool) -> str:
    """`` default_server`` for the platform vhost's listen lines, else ``""``.

    Only the Hop3 platform vhost may carry this flag; per-app vhosts (templated
    elsewhere, in hop3-server) must not, and nginx allows exactly one
    default_server per listen socket. It makes the control plane the deterministic
    owner of unmatched / bare-host requests regardless of include/parse order.
    """
    return " default_server" if default_server else ""


# =============================================================================
# SSL Configuration (shared across all HTTPS configs)
# =============================================================================

SSL_PROTOCOLS = "TLSv1.2 TLSv1.3"
SSL_CIPHERS = (
    "ECDHE-ECDSA-AES128-GCM-SHA256:"
    "ECDHE-RSA-AES128-GCM-SHA256:"
    "ECDHE-ECDSA-AES256-GCM-SHA384:"
    "ECDHE-RSA-AES256-GCM-SHA384"
)

SSL_SETTINGS = f"""    ssl_protocols {SSL_PROTOCOLS};
    ssl_ciphers {SSL_CIPHERS};
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;"""


# =============================================================================
# Proxy Configuration (shared across all proxy locations)
# =============================================================================

PROXY_HEADERS = f"""        proxy_pass http://{HOP3_SERVER_BIND};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;

        # WebSocket support
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";"""


# =============================================================================
# ACME Challenge Location (shared across all configs)
# =============================================================================

ACME_LOCATION = f"""    location /.well-known/acme-challenge/ {{
        root {ACME_WEBROOT};
    }}"""


# =============================================================================
# Template Functions
# =============================================================================


def generate_http_only_config(server_name: str, *, default_server: bool = False) -> str:
    """Generate nginx config for HTTP-only (no SSL).

    Used during initial deployment before SSL is configured.

    Args:
        server_name: The domain name for this server.
        default_server: mark this vhost as nginx's ``default_server`` on :80
            (platform vhost only — see ``_default_server_suffix``).

    Returns:
        Complete nginx configuration string.

    Raises:
        ValueError: if ``server_name`` is not a valid RFC-1035 domain.
    """
    server_name = _validate_server_name(server_name)
    ds = _default_server_suffix(default_server)
    return f"""# Hop3 Server - Reverse Proxy Configuration
# Auto-generated by hop3 installer

server {{
    listen 80{ds};
    server_name {server_name};

{ACME_LOCATION}

    location / {{
{PROXY_HEADERS}
    }}
}}
"""


def generate_https_redirect_config(
    server_name: str, *, default_server: bool = False
) -> str:
    """Generate nginx config for HTTP that redirects to HTTPS.

    Args:
        server_name: The domain name for this server.
        default_server: mark this vhost as nginx's ``default_server`` on :80.

    Returns:
        HTTP server block that redirects to HTTPS.

    Raises:
        ValueError: if ``server_name`` is not a valid RFC-1035 domain.
    """
    server_name = _validate_server_name(server_name)
    ds = _default_server_suffix(default_server)
    return f"""# Redirect HTTP to HTTPS
server {{
    listen 80{ds};
    server_name {server_name};

{ACME_LOCATION}

    location / {{
        return 301 https://$host$request_uri;
    }}
}}
"""


def generate_https_server_config(
    server_name: str,
    ssl_cert: str,
    ssl_key: str,
    *,
    default_server: bool = False,
) -> str:
    """Generate HTTPS server block.

    Args:
        server_name: The domain name for this server.
        ssl_cert: Path to SSL certificate file (fullchain.pem).
        ssl_key: Path to SSL private key file.
        default_server: mark this vhost as nginx's ``default_server`` on :443.

    Returns:
        HTTPS server block configuration.

    Raises:
        ValueError: if ``server_name`` is not a valid RFC-1035 domain.
    """
    server_name = _validate_server_name(server_name)
    ds = _default_server_suffix(default_server)
    return f"""# HTTPS server
server {{
    listen 443 ssl http2{ds};
    server_name {server_name};

    ssl_certificate {ssl_cert};
    ssl_certificate_key {ssl_key};

{SSL_SETTINGS}

    location / {{
{PROXY_HEADERS}
    }}

{ACME_LOCATION}
}}
"""


def generate_full_ssl_config(
    server_name: str,
    ssl_cert: str,
    ssl_key: str,
    *,
    default_server: bool = False,
) -> str:
    """Generate complete nginx config with HTTP redirect and HTTPS.

    This is the standard production configuration that:
    - Redirects all HTTP traffic to HTTPS (except ACME challenges)
    - Serves the application over HTTPS

    Args:
        server_name: The domain name for this server.
        ssl_cert: Path to SSL certificate file (fullchain.pem).
        ssl_key: Path to SSL private key file.
        default_server: mark this vhost as nginx's ``default_server`` on :80
            and :443 (platform vhost only) so unmatched / bare-host requests
            reach the Hop3 control plane instead of an arbitrary app.

    Returns:
        Complete nginx configuration string.
    """
    http_block = generate_https_redirect_config(
        server_name, default_server=default_server
    )
    https_block = generate_https_server_config(
        server_name, ssl_cert, ssl_key, default_server=default_server
    )

    return f"""# Hop3 Server - Reverse Proxy Configuration
# Auto-generated by hop3 installer

{http_block}
{https_block}
"""


# =============================================================================
# Sudoers Configuration
# =============================================================================

SUDOERS_CONTENT = """# Hop3 service management permissions
# Allow hop3 user to reload/restart nginx for deployments
hop3 ALL=(ALL) NOPASSWD: /usr/bin/systemctl reload nginx
hop3 ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart nginx
hop3 ALL=(ALL) NOPASSWD: /usr/sbin/nginx -s reload
hop3 ALL=(ALL) NOPASSWD: /usr/sbin/nginx -t
"""


# =============================================================================
# Systemd Units
# =============================================================================

SYSTEMD_UNIT = """[Unit]
Description=Hop3 Server
After=network.target postgresql.service

[Service]
Type=simple
User=hop3
Group=hop3
WorkingDirectory=/home/hop3
EnvironmentFile=/etc/default/hop3
ExecStart=/home/hop3/venv/bin/hop3-server serve
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""

UWSGI_UNIT = """[Unit]
Description=uWSGI Emperor for Hop3
After=network.target

[Service]
Type=notify
User=hop3
Group=hop3
ExecStart=/home/hop3/venv/bin/uwsgi --emperor /home/hop3/uwsgi-enabled --stats /tmp/hop3-uwsgi-stats.sock
Restart=always
KillSignal=SIGQUIT
NotifyAccess=all

[Install]
WantedBy=multi-user.target
"""
