#!/bin/bash
# Check status of the hop3 development environment

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

cd "$SCRIPT_DIR"

echo "========================================="
echo "Hop3 Development Environment Status"
echo "========================================="
echo ""

# Docker container status
echo "📦 Container Status:"
docker compose ps
echo ""

# Check if container is running
if ! docker compose ps | grep -q "Up"; then
    echo "❌ Container is not running"
    echo "Start it with: ./start.sh"
    exit 0
fi

# Supervisor status (services inside container)
echo "🔧 Services Status (inside container):"
docker compose exec -T hop3-dev supervisorctl status || true
echo ""

# Hop3 apps status
echo "📱 Deployed Apps:"
docker compose exec -T -u hop3 hop3-dev bash -c "
    if command -v hop &> /dev/null; then
        hop app:list 2>/dev/null || echo 'No apps deployed yet'
    else
        echo 'hop CLI not available'
    fi
" || echo "Unable to query apps"
echo ""

echo "========================================="
echo ""
echo "Quick commands:"
echo "  • View logs:      ./logs.sh [service]"
echo "  • Shell access:   ./shell.sh"
echo "  • Stop:           ./stop.sh"
echo ""
