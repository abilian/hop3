#!/bin/bash
set -e
echo "Preparing Radicale..."
mkdir -p collections

# Create requirements.txt for Python toolchain detection.
# The [bcrypt] extra pulls in the bcrypt module, needed both for Radicale's
# htpasswd bcrypt verification and for hashing the admin password in setup.
cat > requirements.txt << 'EOF'
radicale[bcrypt]
EOF

echo "Radicale directories and requirements created"
