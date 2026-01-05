#!/bin/bash
# Open a shell inside the hop3 development container

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

cd "$SCRIPT_DIR"

# Check if container is running
if ! docker compose ps | grep -q "Up"; then
    echo "❌ Error: Container is not running"
    echo "Start it with: ./start.sh"
    exit 1
fi

echo "🐚 Opening shell in hop3-dev container..."
echo "   (You are now the 'hop3' user with hop3-server installed)"
echo ""

# Execute as the hop3 user
docker compose exec -u hop3 hop3-dev /bin/bash
