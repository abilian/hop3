#!/bin/bash
set -e
echo "Preparing Radicale..."
mkdir -p collections

# Create requirements.txt for Python toolchain detection
cat > requirements.txt << 'EOF'
radicale
EOF

echo "Radicale directories and requirements created"
