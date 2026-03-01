#!/bin/bash
set -e

# Required environment variables - fail fast if not set
: "${PORT:?ERROR: PORT is required}"
: "${PGHOST:?ERROR: PGHOST is required}"
: "${PGPORT:?ERROR: PGPORT is required}"
: "${PGDATABASE:?ERROR: PGDATABASE is required}"
: "${PGUSER:?ERROR: PGUSER is required}"
: "${PGPASSWORD:?ERROR: PGPASSWORD is required}"

# Optional with defaults (non-critical)
export XWIKI_DATA_DIR="${XWIKI_DATA_DIR:-/var/lib/xwiki/data}"
export JAVA_OPTS="${JAVA_OPTS:--Xmx1024m}"

# Generate hibernate config from template
envsubst < /opt/xwiki/webapps/xwiki/WEB-INF/hibernate.cfg.xml.template \
    > /opt/xwiki/webapps/xwiki/WEB-INF/hibernate.cfg.xml

# Configure permanent directory
mkdir -p "${XWIKI_DATA_DIR}"
cat > /opt/xwiki/webapps/xwiki/WEB-INF/xwiki.properties << EOF
environment.permanentDirectory=${XWIKI_DATA_DIR}
EOF

# Set Jetty port
sed -i "s/jetty.http.port=8080/jetty.http.port=${PORT}/" /opt/xwiki/start_xwiki.sh

# Ensure proper ownership
chown -R xwiki:xwiki /var/lib/xwiki /opt/xwiki

# Run XWiki as xwiki user (XWIKI_NONINTERACTIVE skips Java version prompts)
cd /opt/xwiki
export XWIKI_NONINTERACTIVE=true
exec su xwiki -c "XWIKI_NONINTERACTIVE=true JAVA_OPTS=\"${JAVA_OPTS}\" ./start_xwiki.sh"
