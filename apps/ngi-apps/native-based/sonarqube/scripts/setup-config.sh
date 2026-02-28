#!/bin/bash
set -e
cd "$(dirname "$0")/.."

# Create data directories
mkdir -p data logs temp extensions

# Write sonar.properties configuration
cat > conf/sonar.properties << EOF
# Database configuration (Hop3 injects PG* vars)
sonar.jdbc.url=jdbc:postgresql://${PGHOST:-localhost}:${PGPORT:-5432}/${PGDATABASE:-sonarqube}
sonar.jdbc.username=${PGUSER:-sonarqube}
sonar.jdbc.password=${PGPASSWORD:-}

# Web Server
sonar.web.host=${BIND_ADDRESS:-127.0.0.1}
sonar.web.port=${PORT:-9000}

# Paths (relative to SonarQube installation)
sonar.path.data=data
sonar.path.logs=logs
sonar.path.temp=temp

# Elasticsearch (embedded)
sonar.search.javaAdditionalOpts=${SONAR_SEARCH_JAVAADDITIONALOPTS:--Dnode.store.allow_mmap=false}
EOF

echo "SonarQube configuration ready"
