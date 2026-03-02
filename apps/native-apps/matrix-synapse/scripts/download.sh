#!/bin/bash
set -e
echo "Preparing Matrix Synapse..."
mkdir -p data media_store

# Create requirements.txt for Python toolchain detection
cat > requirements.txt << 'EOF'
matrix-synapse[postgres]
EOF

echo "Matrix Synapse directories and requirements created"
