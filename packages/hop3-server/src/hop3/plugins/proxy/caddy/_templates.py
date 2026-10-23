# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

# What an app's site serves, on whichever scheme it is reached.
CADDY_SITE_BODY = """
    $HOP3_INTERNAL_CADDY_GATE
    $HOP3_INTERNAL_CADDY_ACME
    $HOP3_INTERNAL_CADDY_REQUEST_BODY
    $HOP3_INTERNAL_CADDY_DENY
    $HOP3_INTERNAL_CADDY_CUSTOM_CLAUSES
    $HOP3_INTERNAL_CADDY_STATIC_MAPPINGS
    $HOP3_INTERNAL_CADDY_CACHE_MAPPINGS
    $HOP3_INTERNAL_CADDY_BLOCK_GIT
    $HOP3_INTERNAL_CADDY_PORTMAP
"""

# Plain HTTP allowed ([deploy].allow-http). Every address names its scheme,
# since to Caddy a bare hostname means HTTPS only, and the two schemes are
# two blocks, since Caddy refuses `tls` in a block that listens on HTTP.
CADDY_TEMPLATE = """
$HOP3_INTERNAL_CADDY_HTTP_SITES {
    $HOP3_INTERNAL_CADDY_SITE
}

$HOP3_INTERNAL_CADDY_HTTPS_SITES {
    $HOP3_INTERNAL_CADDY_TLS
    $HOP3_INTERNAL_CADDY_SITE
}
"""

# HTTPS-only template (HTTP to HTTPS redirect). The redirect sits in a
# catch-all `handle` so the ACME challenge, a more specific `handle`, is
# answered on plain HTTP first: `redir` alone runs before any `handle`.
CADDY_HTTPS_ONLY_TEMPLATE = """
$HOP3_INTERNAL_CADDY_HTTP_SITES {
    $HOP3_INTERNAL_CADDY_ACME
    handle {
        redir https://{host}{uri} permanent
    }
}

$HOP3_INTERNAL_CADDY_HTTPS_SITES {
    $HOP3_INTERNAL_CADDY_TLS
    $HOP3_INTERNAL_CADDY_SITE
}
"""

# Reverse proxy configuration fragment. Caddy sets X-Forwarded-For, -Proto
# and -Host itself, replacing whatever an untrusted client sent; overriding
# them here sent `{remote}`, which is `ip:port`, as the client address.
CADDY_PORTMAP_FRAGMENT = """
    reverse_proxy $CADDY_BACKEND {
        header_up X-Real-IP {remote_host}
        header_up X-Request-Start {time.now.unix_ms}
        $CADDY_ACL
    }
"""

# A php-fpm pool speaks FastCGI. `php_fastcgi` serves the front controller
# the way the nginx fragment does: an existing file, else `index.php`. Hidden
# files in the tree are refused as nginx refuses them (see its fragment); the
# character class spells the dot without a backslash for the Caddyfile lexer.
CADDY_FASTCGI_FRAGMENT = """
    @hop3_hidden {
        path_regexp /[.]
        not path /.well-known/*
    }
    respond @hop3_hidden 404
    root * $PHP_DOCUMENT_ROOT
    php_fastcgi $CADDY_BACKEND
    file_server
"""

# The ACME HTTP-01 webroot every proxy serves (see platform/certificates.py).
CADDY_ACME_CHALLENGE = """
    handle /.well-known/acme-challenge/* {
        root * $ACME_WWW
        file_server
    }
"""

# Static file serving configuration. `{path}/` lets file_server redirect a
# directory asked for without its slash (308, relative, prefix kept), as the
# nginx mapping does.
HOP3_INTERNAL_CADDY_STATIC_MAPPING = """
    handle_path $static_url* {
        root * $static_path
        file_server
        try_files {path} {path}/ {path}.html
    }
"""

# Paths the app lists in [proxy] deny, each with everything beneath it.
# Caddy's directive order runs `respond` before reverse_proxy, php_fastcgi
# and file_server, so a denied path never reaches the app or the disk.
CADDY_DENY = """
    @hop3_denied path $paths
    respond @hop3_denied 404
"""

# Largest request body this app accepts ([proxy] max-body-size).
CADDY_REQUEST_BODY = """
    request_body {
        max_size $max_body_size
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
        reverse_proxy $CADDY_BACKEND
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

# The access gate (ADR 062). `forward_auth` runs before every `handle` in
# Caddy's directive order, so static paths are checked too. On a 2xx it deletes
# each copied header from the request and sets the ones the check returned;
# otherwise the check's own answer (the sign-in redirect, a 403) goes to the
# client. `/_hop3/auth/` is hop3-server's, on the app's host.
CADDY_GATE = """
    @hop3_gated not path /_hop3/auth/*
    forward_auth @hop3_gated $upstream {
        uri /auth/check?redirect=1
        header_up X-Hop3-App $APP
        copy_headers $headers
    }
    handle /_hop3/auth/* {
        reverse_proxy $upstream {
            header_up X-Hop3-App $APP
        }
    }
"""
