#!/bin/bash
# Stop the hop3 development environment

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "🛑 Stopping hop3 development environment..."

cd "$SCRIPT_DIR"
docker compose stop

echo "✅ Environment stopped"
echo ""
echo "To start again:  ./start.sh"
echo "To remove all data: docker compose down -v"
echo ""
