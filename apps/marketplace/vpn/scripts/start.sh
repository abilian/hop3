#!/bin/bash
# VPN start script for Hop3

set -eu

DATA_DIR="${HOP3_DATA_DIR:-/app/data}"
VPN_USER="${VPN_USER:-vpn}"

mkdir -p /run/vpn /run/dnsmasq/hosts

export APP_ORIGIN="${HOP3_APP_ORIGIN:-http://localhost:3000}"
export APP_DOMAIN="${HOP3_APP_DOMAIN:-localhost}"
export DATA_DIR="${DATA_DIR}"
export RUN_DIR=/run/vpn
export SERVER_NAME=hop3
export VPN_USER="${VPN_USER}"

echo "==> Fixing permissions"
chown -R ${VPN_USER}:${VPN_USER} "${DATA_DIR}" /run/vpn

echo "Starting VPN"
exec /usr/bin/supervisord --configuration /etc/supervisor/supervisord.conf --nodaemon -i OpenVPN
