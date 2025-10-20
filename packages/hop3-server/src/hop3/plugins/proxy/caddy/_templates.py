# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

# Basic Caddy configuration template
CADDY_TEMPLATE = """
$HOST_NAME {
    $HOP3_INTERNAL_CADDY_TLS
    $HOP3_INTERNAL_CADDY_CUSTOM_CLAUSES
    $HOP3_INTERNAL_CADDY_STATIC_MAPPINGS
    $HOP3_INTERNAL_CADDY_CACHE_MAPPINGS
    $HOP3_INTERNAL_CADDY_BLOCK_GIT
    $HOP3_INTERNAL_CADDY_PORTMAP
}
"""

# HTTPS-only template (HTTP to HTTPS redirect)
CADDY_HTTPS_ONLY_TEMPLATE = """
http://$HOST_NAME {
    redir https://{host}{uri} permanent
}

https://$HOST_NAME {
    $HOP3_INTERNAL_CADDY_TLS
    $HOP3_INTERNAL_CADDY_CUSTOM_CLAUSES
    $HOP3_INTERNAL_CADDY_STATIC_MAPPINGS
    $HOP3_INTERNAL_CADDY_CACHE_MAPPINGS
    $HOP3_INTERNAL_CADDY_BLOCK_GIT
    $HOP3_INTERNAL_CADDY_PORTMAP
}
"""

# Reverse proxy configuration fragment
CADDY_PORTMAP_FRAGMENT = """
    reverse_proxy $CADDY_BACKEND {
        header_up X-Forwarded-Proto {scheme}
        header_up X-Forwarded-For {remote}
        header_up X-Real-IP {remote}
        header_up X-Request-Start {time.now.unix_ms}
        $CADDY_ACL
    }
"""

# Static file serving configuration
HOP3_INTERNAL_CADDY_STATIC_MAPPING = """
    handle_path $static_url* {
        root * $static_path
        file_server
        try_files {path} {path}/index.html {path}.html
    }
"""

# Git folder blocking configuration
CADDY_BLOCK_GIT = """
    handle /.git* {
        respond 403
    }
"""

# Cache configuration (using Caddy's cache plugin if available)
HOP3_INTERNAL_CADDY_CACHE_MAPPING = """
    @cached {
        path_regexp ^/($cache_prefixes)
    }
    handle @cached {
        header Cache-Control "public, max-age=$cache_time_control"
        header X-Cache-Status "HIT"
        reverse_proxy $CADDY_BACKEND {
            header_up X-Forwarded-Proto {scheme}
            header_up X-Forwarded-For {remote}
        }
    }
"""

# TLS configuration fragment
CADDY_TLS_MANUAL = """
    tls $CADDY_ROOT/$APP.crt $CADDY_ROOT/$APP.key
"""

# TLS with automatic certificate management (Let's Encrypt)
CADDY_TLS_AUTO = """
    tls {
        email $CADDY_ACME_EMAIL
    }
"""

# Compression configuration
CADDY_COMPRESSION = """
    encode gzip zstd
"""
