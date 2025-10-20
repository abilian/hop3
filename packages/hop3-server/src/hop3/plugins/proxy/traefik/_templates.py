# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

# Basic Traefik configuration template (YAML format)
TRAEFIK_TEMPLATE = """
http:
  routers:
    $APP-router:
      rule: "Host(`$HOST_NAME`)"
      service: "$APP-service"
      entryPoints:
        - web
        - websecure
      tls:
        certResolver: hop3
      middlewares:
        - $APP-compression
        $HOP3_INTERNAL_TRAEFIK_MIDDLEWARES

  services:
    $APP-service:
      loadBalancer:
        servers:
          - url: "$TRAEFIK_BACKEND"

  middlewares:
    $APP-compression:
      compress: {}
    $HOP3_INTERNAL_TRAEFIK_CUSTOM_MIDDLEWARES
"""

# HTTPS-only template (HTTP to HTTPS redirect)
TRAEFIK_HTTPS_ONLY_TEMPLATE = """
http:
  routers:
    $APP-http-router:
      rule: "Host(`$HOST_NAME`)"
      entryPoints:
        - web
      middlewares:
        - $APP-https-redirect
      service: "$APP-service"

    $APP-https-router:
      rule: "Host(`$HOST_NAME`)"
      entryPoints:
        - websecure
      service: "$APP-service"
      tls:
        certResolver: hop3
      middlewares:
        - $APP-compression
        $HOP3_INTERNAL_TRAEFIK_MIDDLEWARES

  services:
    $APP-service:
      loadBalancer:
        servers:
          - url: "$TRAEFIK_BACKEND"

  middlewares:
    $APP-https-redirect:
      redirectScheme:
        scheme: https
        permanent: true

    $APP-compression:
      compress: {}

    $HOP3_INTERNAL_TRAEFIK_CUSTOM_MIDDLEWARES
"""

# Static file serving middleware (uses replacePath)
HOP3_INTERNAL_TRAEFIK_STATIC_ROUTER = """
    $APP-static-$static_index:
      rule: "Host(`$HOST_NAME`) && PathPrefix(`$static_url`)"
      service: "$APP-static-$static_index-service"
      entryPoints:
        - web
        - websecure
      priority: 100
      tls:
        certResolver: hop3
"""

HOP3_INTERNAL_TRAEFIK_STATIC_SERVICE = """
    $APP-static-$static_index-service:
      loadBalancer:
        servers:
          - url: "file://$static_path"
"""

# Git folder blocking middleware
TRAEFIK_BLOCK_GIT_MIDDLEWARE = """
    $APP-block-git:
      replacePathRegex:
        regex: "^\\.git.*"
        replacement: "/403"
"""

# Cache headers middleware
HOP3_INTERNAL_TRAEFIK_CACHE_MIDDLEWARE = """
    $APP-cache-headers:
      headers:
        customResponseHeaders:
          Cache-Control: "public, max-age=$cache_time_control"
          X-Cache-Status: "HIT"
"""

# TLS configuration with manual certificates
TRAEFIK_TLS_MANUAL = """
tls:
  certificates:
    - certFile: $TRAEFIK_ROOT/$APP.crt
      keyFile: $TRAEFIK_ROOT/$APP.key
"""

# Additional headers middleware
TRAEFIK_HEADERS_MIDDLEWARE = """
    $APP-headers:
      headers:
        customResponseHeaders:
          X-Deployed-By: "Hop3"
        customRequestHeaders:
          X-Forwarded-Proto: "https"
"""

# IP allowlist middleware template
TRAEFIK_IP_ALLOWLIST = """
    $APP-ip-allowlist:
      ipAllowList:
        sourceRange:
          $TRAEFIK_ACL
"""
