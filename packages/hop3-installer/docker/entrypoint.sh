#!/bin/bash
# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# Entrypoint script for Hop3 test containers
# Supports two modes:
#   - sleep: Keep container running for installer testing (default)
#   - supervisor: Run services after hop3 installation

set -e

MODE=${HOP3_DOCKER_MODE:-sleep}

echo "========================================"
echo "Hop3 Test Container"
echo "Mode: $MODE"
echo "========================================"

case "$MODE" in
    sleep)
        # Default mode: just keep the container running
        # Used during installation phase
        echo "Running in sleep mode (for installer testing)"
        exec sleep infinity
        ;;
    supervisor)
        # Service mode: run supervisor to manage all services
        # Used after hop3 installation is complete
        echo "Running in supervisor mode (services managed)"

        # Check if supervisor config exists
        if [ ! -f /etc/supervisor/conf.d/hop3.conf ]; then
            echo "ERROR: Supervisor config not found at /etc/supervisor/conf.d/hop3.conf"
            echo "Run the hop3-deploy post-install step to generate it."
            exit 1
        fi

        # Ensure log directories exist with correct permissions
        mkdir -p /var/log/supervisor

        # Start supervisor in foreground
        exec /usr/bin/supervisord -n -c /etc/supervisor/supervisord.conf
        ;;
    *)
        echo "ERROR: Unknown mode: $MODE"
        echo "Supported modes: sleep, supervisor"
        exit 1
        ;;
esac
