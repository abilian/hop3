#!/bin/bash
# Test that the hop3 development environment is working

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

cd "$SCRIPT_DIR"

echo "🧪 Testing Hop3 Development Environment"
echo "========================================"
echo ""

# Check if container is running
if ! docker compose ps | grep -q "Up"; then
    echo "❌ Container is not running"
    echo "Start it with: ./start.sh"
    exit 1
fi

echo "✅ Container is running"
echo ""

# Test SSH
echo "📡 Testing SSH (port 2222)..."
if timeout 2 bash -c "</dev/tcp/localhost/2222" 2>/dev/null; then
    echo "✅ SSH is accessible"
else
    echo "❌ SSH is not accessible"
fi
echo ""

# Test HTTP
echo "🌐 Testing HTTP (port 8080)..."
HTTP_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080 2>/dev/null || echo "000")
if [ "$HTTP_RESPONSE" = "200" ]; then
    echo "✅ HTTP is accessible"
    echo "   Response: $(curl -s http://localhost:8080)"
elif [ "$HTTP_RESPONSE" = "000" ]; then
    echo "❌ HTTP is not accessible (connection failed)"
else
    echo "⚠️  HTTP returned status $HTTP_RESPONSE"
fi
echo ""

# Test PostgreSQL
echo "🐘 Testing PostgreSQL (port 5432)..."
if timeout 2 bash -c "</dev/tcp/localhost/5432" 2>/dev/null; then
    echo "✅ PostgreSQL is accessible"
else
    echo "❌ PostgreSQL is not accessible"
fi
echo ""

# Check service status inside container
echo "🔧 Checking services inside container..."
docker compose exec -T hop3-dev supervisorctl status
echo ""

echo "========================================"
if [ "$HTTP_RESPONSE" = "200" ]; then
    echo "✅ All core services are working!"
    echo ""
    echo "Next steps:"
    echo "  1. Deploy an app: ./deploy.sh myapp /path/to/app"
    echo "  2. Access it at: http://localhost:8080/myapp"
else
    echo "⚠️  Some services may not be ready yet"
    echo "   Check logs: ./logs.sh"
    echo "   View status: ./status.sh"
fi
echo ""
