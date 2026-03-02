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
export SONAR_DATA_DIR="${SONAR_DATA_DIR:-/var/lib/sonarqube/data}"
export SONAR_EXTENSIONS_DIR="${SONAR_EXTENSIONS_DIR:-/var/lib/sonarqube/extensions}"
export SONAR_LOGS_DIR="${SONAR_LOGS_DIR:-/var/lib/sonarqube/logs}"
export SONAR_TEMP_DIR="${SONAR_TEMP_DIR:-/var/lib/sonarqube/temp}"

# Write sonar.properties
cat > /opt/sonarqube/conf/sonar.properties << EOF
# Database
sonar.jdbc.url=jdbc:postgresql://${PGHOST}:${PGPORT}/${PGDATABASE}
sonar.jdbc.username=${PGUSER}
sonar.jdbc.password=${PGPASSWORD}

# Web Server
sonar.web.host=0.0.0.0
sonar.web.port=${PORT}

# Paths
sonar.path.data=${SONAR_DATA_DIR}
sonar.path.logs=${SONAR_LOGS_DIR}
sonar.path.temp=${SONAR_TEMP_DIR}

# Elasticsearch (embedded)
sonar.search.javaAdditionalOpts=${SONAR_SEARCH_JAVAADDITIONALOPTS:--Dnode.store.allow_mmap=false}
EOF

# Ensure proper ownership
chown -R sonarqube:sonarqube /var/lib/sonarqube /opt/sonarqube/conf

# Run SonarQube as sonarqube user
cd /opt/sonarqube
exec su sonarqube -c "/opt/sonarqube/bin/linux-x86-64/sonar.sh console"
