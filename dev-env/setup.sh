#!/bin/bash
# Setup script for hop3 development environment

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "========================================="
echo "Hop3 Development Environment Setup"
echo "========================================="
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Error: Docker is not installed."
    echo "Please install Docker Desktop from: https://www.docker.com/products/docker-desktop"
    exit 1
fi

# Check if Docker Compose is available
if ! docker compose version &> /dev/null; then
    echo "❌ Error: Docker Compose is not available."
    echo "Please ensure Docker Desktop is running and up to date."
    exit 1
fi

echo "✅ Docker is installed and running"
echo ""

# Build the Docker image (it will build hop3-server inside)
echo "🐳 Building hop3-dev Docker image..."
echo "   (This may take 5-10 minutes on first run)"
echo "   The image will build hop3-server from source automatically"
cd "$SCRIPT_DIR"
docker compose build

echo "✅ Docker image built successfully"
echo ""

echo "========================================="
echo "✅ Setup Complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "  1. Start the environment:  ./start.sh"
echo "  2. Check status:           ./status.sh"
echo "  3. Access the shell:       ./shell.sh"
echo "  4. Deploy an app:          ./deploy.sh <app-name> <app-directory>"
echo "  5. View logs:              ./logs.sh [service]"
echo "  6. Stop the environment:   ./stop.sh"
echo ""
