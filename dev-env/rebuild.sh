#!/bin/bash
# Rebuild hop3-server package and Docker image

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "🔧 Rebuilding hop3 development environment..."
echo ""

# Rebuild Docker image (it will rebuild hop3-server inside)
echo "🐳 Rebuilding Docker image (includes hop3-server build)..."
cd "$SCRIPT_DIR"
docker compose build

echo "✅ Docker image rebuilt"
echo ""

# Ask if they want to restart
read -p "Restart the container now? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker compose down
    ./start.sh
fi

echo ""
echo "✅ Rebuild complete!"
