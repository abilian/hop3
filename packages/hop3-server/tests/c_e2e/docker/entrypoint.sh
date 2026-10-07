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
# PostgreSQL runs under supervisor, as the postgres user and in the foreground,
# under the name its systemd unit has, so `supervisorctl restart postgresql`
# and `systemctl restart postgresql` name the same thing (see
# notes/lessons-learned/e2e-test-infrastructure.md). The cluster was
# configured at image build through the installer's own module.
PG_VER=$(ls /etc/postgresql | head -1)
mkdir -p /var/run/postgresql && chown postgres:postgres /var/run/postgresql

# An admin domain, when a test asks for one: the access gate signs users in
# there (ADR 062). A certificate for it, ADMIN_DOMAIN for hop3-server, and a
# route to hop3-server on whichever proxy runs, as the installer sets one up
# for nginx on a real server.
ADMIN_DOMAIN="${HOP3_E2E_ADMIN_DOMAIN:-}"
ADMIN_ENV=""
if [ -n "$ADMIN_DOMAIN" ]; then
    mkdir -p /home/hop3/admin-tls
    openssl req -x509 -newkey rsa:2048 -nodes -days 2 -subj "/CN=$ADMIN_DOMAIN" \
        -addext "subjectAltName=DNS:$ADMIN_DOMAIN" \
        -keyout /home/hop3/admin-tls/admin.key \
        -out /home/hop3/admin-tls/admin.crt 2>/dev/null
    chown -R hop3:hop3 /home/hop3/admin-tls
    ADMIN_ENV=",ADMIN_DOMAIN=\"$ADMIN_DOMAIN\""
fi

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

[program:hop3-rootd]
command=/home/hop3/venv/bin/hop3-rootd --socket-path /run/hop3-rootd/socket
autostart=true
autorestart=true
priority=1
stdout_logfile=/var/log/supervisor/hop3-rootd.log
stderr_logfile=/var/log/supervisor/hop3-rootd_err.log

[program:postgresql]
command=/usr/lib/postgresql/${PG_VER}/bin/postgres -D /var/lib/postgresql/${PG_VER}/main -c config_file=/etc/postgresql/${PG_VER}/main/postgresql.conf
user=postgres
priority=1
autostart=true
autorestart=true
stdout_logfile=/var/log/supervisor/postgresql.log
stderr_logfile=/var/log/supervisor/postgresql_err.log

[program:sshd]
command=/usr/sbin/sshd -D
autostart=true
autorestart=true
stdout_logfile=/var/log/supervisor/sshd.log
stderr_logfile=/var/log/supervisor/sshd_err.log

[program:uwsgi-hop3]
command=/usr/bin/uwsgi-core --emperor /home/hop3/uwsgi-enabled
directory=/home/hop3
user=hop3
autostart=true
autorestart=true
stdout_logfile=/var/log/supervisor/uwsgi.log
stderr_logfile=/var/log/supervisor/uwsgi_err.log

[program:hop3-server]
command=/home/hop3/venv/bin/hop3-server serve
directory=/home/hop3
user=hop3
autostart=true
autorestart=true
environment=HOME="/home/hop3",HOP3_SECRET_KEY="e2e-test-secret-key-do-not-use-in-production",HOP3_UNSAFE="true",HOP3_UNSAFE_ACK="yes-I-understand",HOP3_DB_URL="sqlite:////home/hop3/hop3.db",ACME_ENGINE="self-signed",HOP3_PROXY_TYPE="$PROXY_TYPE"$ADMIN_ENV
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
environment=HOME="/home/hop3"
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
        # Traefik reads each app's routes from the directory the plugin
        # writes them to (hop3's TRAEFIK_ROOT), and applies changes on its own.
        mkdir -p /home/hop3/traefik
        chown hop3:hop3 /home/hop3/traefik
        cat > /etc/traefik/traefik.yml <<'TRAEFIK_EOF'
# Traefik static configuration
# aliasHeadersStrategy: a WSGI or PHP backend reads X_Hop3_User as the
# X-Hop3-User header the access gate sets; delete such aliases on the way in.
entryPoints:
  web:
    address: ":80"
    http:
      aliasHeadersStrategy: delete
  websecure:
    address: ":443"
    http:
      aliasHeadersStrategy: delete

providers:
  file:
    directory: /home/hop3/traefik
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

if [ -n "$ADMIN_DOMAIN" ]; then
    echo "Routing admin domain $ADMIN_DOMAIN to hop3-server..."
    case "$PROXY_TYPE" in
        nginx)
            cat > /etc/nginx/sites-enabled/hop3-admin <<ADMIN_EOF
server {
  listen 443 ssl;
  server_name $ADMIN_DOMAIN;
  ssl_certificate /home/hop3/admin-tls/admin.crt;
  ssl_certificate_key /home/hop3/admin-tls/admin.key;
  location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host \$host;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
  }
}
ADMIN_EOF
            ;;
        caddy)
            cat >> /home/hop3/caddy/Caddyfile <<ADMIN_EOF

https://$ADMIN_DOMAIN {
    tls /home/hop3/admin-tls/admin.crt /home/hop3/admin-tls/admin.key
    reverse_proxy 127.0.0.1:8000
}
ADMIN_EOF
            ;;
        traefik)
            cat > /home/hop3/traefik/_admin.yml <<ADMIN_EOF
http:
  routers:
    hop3-admin:
      rule: "Host(\`$ADMIN_DOMAIN\`)"
      entryPoints: [websecure]
      service: hop3-admin
      tls: {}
  services:
    hop3-admin:
      loadBalancer:
        servers:
          - url: "http://127.0.0.1:8000"
tls:
  certificates:
    - certFile: /home/hop3/admin-tls/admin.crt
      keyFile: /home/hop3/admin-tls/admin.key
ADMIN_EOF
            chown hop3:hop3 /home/hop3/traefik/_admin.yml
            ;;
    esac
fi

echo "Starting supervisord..."
exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf
