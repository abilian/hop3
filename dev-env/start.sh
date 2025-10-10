#!/bin/bash
# Start the hop3 development environment

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "🚀 Starting hop3 development environment..."
echo ""

cd "$SCRIPT_DIR"

# Start the container
docker compose up -d

echo ""
echo "⏳ Waiting for services to be ready..."
sleep 5

# Wait for health check
max_wait=30
elapsed=0
while [ $elapsed -lt $max_wait ]; do
    if docker compose ps | grep -q "healthy"; then
        echo "✅ Services are healthy!"
        break
    fi
    echo "   Still waiting... ($elapsed/$max_wait seconds)"
    sleep 2
    elapsed=$((elapsed + 2))
done

if [ $elapsed -ge $max_wait ]; then
    echo "⚠️  Warning: Services may not be fully ready yet"
    echo "   Check status with: ./status.sh"
fi

echo ""
echo "========================================="
echo "✅ Environment Started!"
echo "========================================="
echo ""
echo "Services available:"
echo "  • hop3-server API:  http://localhost:8000 (JSON-RPC)"
echo "  • SSH:              localhost:2222 (hop3/hop3)"
echo "  • HTTP (nginx):     http://localhost:8080"
echo "  • HTTPS (nginx):    https://localhost:8443"
echo "  • PostgreSQL:       localhost:5432"
echo ""
echo "Quick commands:"
echo "  • Test services:  ./test.sh"
echo "  • Shell access:   ./shell.sh"
echo "  • Check status:   ./status.sh"
echo "  • View logs:      ./logs.sh"
echo "  • Stop:           ./stop.sh"
echo ""
echo "💡 Run './test.sh' to verify all services are working"
echo ""
