#!/bin/bash
# Run a command inside the hop3 development container

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

cd "$SCRIPT_DIR"

# Check if container is running
if ! docker compose ps | grep -q "Up"; then
    echo "❌ Error: Container is not running"
    echo "Start it with: ./start.sh"
    exit 1
fi

if [ "$#" -eq 0 ]; then
    echo "Usage: ./run.sh <command> [args...]"
    echo ""
    echo "Examples:"
    echo "  ./run.sh hop app:list"
    echo "  ./run.sh hop app:status myapp"
    echo "  ./run.sh hop app:logs myapp"
    echo "  ./run.sh hop app:start myapp"
    echo "  ./run.sh hop app:stop myapp"
    echo ""
    exit 1
fi

# Execute command as hop3 user
docker compose exec -u hop3 hop3-dev "$@"
