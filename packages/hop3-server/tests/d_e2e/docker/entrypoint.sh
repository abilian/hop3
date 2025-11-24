#!/bin/bash
# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# Entrypoint script for Hop3 E2E test containers
# Dynamically configures supervisord based on HOP3_PROXY_TYPE

set -e

# Default to nginx if not specified
PROXY_TYPE=${HOP3_PROXY_TYPE:-nginx}

echo "========================================"
echo "Starting Hop3 E2E container"
echo "Proxy type: $PROXY_TYPE"
echo "========================================"

# Generate supervisord configuration based on proxy type
# NOTE: Use <<EOF (without quotes) to allow variable expansion
cat > /etc/supervisor/supervisord.conf <<EOF
[supervisord]
nodaemon=true
logfile=/var/log/supervisor/supervisord.log
pidfile=/var/run/supervisord.pid

[unix_http_server]
file=/var/run/supervisor.sock

[supervisorctl]
serverurl=unix:///var/run/supervisor.sock

[rpcinterface:supervisor]
supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface

[program:sshd]
command=/usr/sbin/sshd -D
autostart=true
autorestart=true
stdout_logfile=/var/log/supervisor/sshd.log
stderr_logfile=/var/log/supervisor/sshd_err.log

[program:uwsgi]
command=/usr/bin/uwsgi-core --emperor /home/hop3/uwsgi-enabled
directory=/home/hop3
user=hop3
autostart=true
autorestart=true
stdout_logfile=/var/log/supervisor/uwsgi.log
stderr_logfile=/var/log/supervisor/uwsgi_err.log

[program:hop3-server]
command=/home/hop3/venv/bin/hop-server serve
directory=/home/hop3
user=hop3
autostart=true
autorestart=true
environment=HOME="/home/hop3",HOP3_SECRET_KEY="e2e-test-secret-key-do-not-use-in-production",HOP3_UNSAFE="true",HOP3_DB_URL="sqlite:////home/hop3/hop3.db",ACME_ENGINE="self-signed",HOP3_PROXY_TYPE="$PROXY_TYPE",HOP3_E2E_TEST="true"
stdout_logfile=/var/log/supervisor/hop3-server.log
stderr_logfile=/var/log/supervisor/hop3-server_err.log

EOF

# Add proxy-specific configuration
case "$PROXY_TYPE" in
    nginx)
        echo "Configuring Nginx proxy..."
        cat >> /etc/supervisor/supervisord.conf <<'EOF'
[program:nginx]
command=/usr/sbin/nginx -g "daemon off;"
autostart=true
autorestart=true
stdout_logfile=/var/log/supervisor/nginx.log
stderr_logfile=/var/log/supervisor/nginx_err.log

EOF
        ;;
    caddy)
        echo "Configuring Caddy proxy..."
        cat >> /etc/supervisor/supervisord.conf <<'EOF'
[program:caddy]
command=/usr/bin/caddy run --config /home/hop3/caddy/Caddyfile --adapter caddyfile
directory=/home/hop3
user=hop3
autostart=true
autorestart=true
stdout_logfile=/var/log/supervisor/caddy.log
stderr_logfile=/var/log/supervisor/caddy_err.log

EOF
        # Create Caddy config directory
        mkdir -p /home/hop3/caddy
        chown hop3:hop3 /home/hop3/caddy
        # Create initial Caddyfile
        cat > /home/hop3/caddy/Caddyfile <<'CADDY_EOF'
# Initial Caddyfile - will be extended by hop3 deployments
{
    admin off
    auto_https off
}

# Import all hop3 Caddy configs
import /home/hop3/caddy/*.caddyfile
CADDY_EOF
        chown hop3:hop3 /home/hop3/caddy/Caddyfile
        ;;
    traefik)
        echo "Configuring Traefik proxy..."
        cat >> /etc/supervisor/supervisord.conf <<'EOF'
[program:traefik]
command=/usr/local/bin/traefik --configFile=/etc/traefik/traefik.yml
autostart=true
autorestart=true
stdout_logfile=/var/log/supervisor/traefik.log
stderr_logfile=/var/log/supervisor/traefik_err.log

EOF
        # Create Traefik static config
        mkdir -p /etc/traefik/dynamic
        cat > /etc/traefik/traefik.yml <<'TRAEFIK_EOF'
# Traefik static configuration
entryPoints:
  web:
    address: ":80"
  websecure:
    address: ":443"

providers:
  file:
    directory: /etc/traefik/dynamic
    watch: true

api:
  insecure: false
  dashboard: false

log:
  level: INFO

accessLog: {}
TRAEFIK_EOF
        ;;
    *)
        echo "ERROR: Unknown proxy type: $PROXY_TYPE"
        echo "Supported types: nginx, caddy, traefik"
        exit 1
        ;;
esac

echo "Starting supervisord..."
exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf
