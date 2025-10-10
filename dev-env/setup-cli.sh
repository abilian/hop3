#!/bin/bash
# Setup hop3-cli on your local machine to target the dev container

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "🔧 Setting up hop3-cli to target the dev container"
echo "=================================================="
echo ""

# Check if container is running
cd "$SCRIPT_DIR"
if ! docker compose ps | grep -q "Up"; then
    echo "❌ Container is not running"
    echo "Start it with: ./start.sh"
    exit 1
fi

echo "✅ Container is running"
echo ""

# Install hop3-cli locally if not already installed
echo "📦 Installing hop3-cli locally..."
cd "$PROJECT_ROOT"

# Check if hop3-cli is in packages
if [ -d "packages/hop3-cli" ]; then
    # Install from local source
    uv pip install -e packages/hop3-cli
else
    # Install hop3 CLI from the server package (it includes both)
    uv pip install -e packages/hop3-server
fi

echo "✅ hop3-cli installed"
echo ""

# Create hop3-cli config
echo "⚙️  Creating hop3-cli configuration..."

# Get the config directory (platform-specific)
if [[ "$OSTYPE" == "darwin"* ]]; then
    CONFIG_DIR="$HOME/Library/Application Support/hop3-cli"
else
    CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/hop3-cli"
fi

mkdir -p "$CONFIG_DIR"

cat > "$CONFIG_DIR/config.toml" << 'EOF'
# Hop3 CLI Configuration for Dev Environment

# Point to the dev container's hop3-server JSON-RPC API
api_url = "http://localhost:8000"

# No authentication needed in dev mode (HOP3_ENABLE_AUTH=false in container)
api_token = ""
EOF

echo "✅ Configuration saved to $CONFIG_DIR/config.toml"
echo ""

# Also set environment variable for immediate use
export HOP3_API_URL="http://localhost:8000"

echo "=================================================="
echo "✅ Setup Complete!"
echo "=================================================="
echo ""
echo "The hop CLI is now configured to use the dev container!"
echo ""
echo "Configuration:"
echo "  • API URL:  http://localhost:8000"
echo "  • Auth:     Disabled (dev mode)"
echo "  • Config:   $CONFIG_DIR/config.toml"
echo ""
echo "Now you can deploy apps from your host machine:"
echo ""
echo "  hop deploy myapp /path/to/app"
echo "  hop app:status myapp"
echo "  hop app:logs myapp"
echo ""
echo "Then access via browser:"
echo "  http://localhost:8080/myapp"
echo ""
echo "💡 Tip: Add this to your ~/.bashrc or ~/.zshrc:"
echo "  export HOP3_API_URL='http://localhost:8000'"
echo ""
