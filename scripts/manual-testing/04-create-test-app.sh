#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Step 4: Create a Simple Flask Test Application

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env-manual-test"

# Create a temporary directory for our app
APP_DIR="/tmp/flask-manual-test"
rm -rf $APP_DIR
mkdir -p $APP_DIR

# 1. Create the Flask application file
cat << 'EOF' > $APP_DIR/app.py
from flask import Flask
app = Flask(__name__)
@app.route("/")
def index():
    return "Hello from Manual E2E Test!"
EOF

# 2. Create the requirements file
echo "flask>=3.0" > $APP_DIR/requirements.txt

# 3. Create the Procfile
echo "web: flask --app app run --host 0.0.0.0 --port \$PORT" > $APP_DIR/Procfile

# 4. Create the ENV file to configure the virtual host for nginx
APP_NAME="manual-app-$(date +%s)"
HOSTNAME="${APP_NAME}.test.local"
echo "HOST_NAME=${HOSTNAME}" > $APP_DIR/ENV

# Save environment variables to file for subsequent scripts
cat > "${ENV_FILE}" << ENVEOF
APP_DIR=${APP_DIR}
APP_NAME=${APP_NAME}
HOSTNAME=${HOSTNAME}
HOP3_MANUAL_TEST_KEY=/tmp/hop3-debug-key
ENVEOF

echo "✅ Test application created in: $APP_DIR"
echo "   App name will be: $APP_NAME"
echo "   Hostname will be: $HOSTNAME"
echo "   Environment saved to: ${ENV_FILE}"
