# SonarQube Dockerfile for Hop3
# Code quality and security analysis platform

# Use Debian Trixie (13) which has Java 21 in repositories
FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies (procps needed for ps command used by SonarQube startup)
# SonarQube 26.x requires Java 21
RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-21-jre-headless \
    curl \
    ca-certificates \
    unzip \
    gettext-base \
    gnupg \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Create sonarqube user (UID 1000 for compatibility)
RUN groupadd -g 1000 sonarqube \
    && useradd -u 1000 -g sonarqube -m -d /opt/sonarqube -s /bin/bash sonarqube

# Create directories
RUN mkdir -p /opt/sonarqube /var/lib/sonarqube/data /var/lib/sonarqube/extensions /var/lib/sonarqube/logs /var/lib/sonarqube/temp \
    && chown -R sonarqube:sonarqube /opt/sonarqube /var/lib/sonarqube

WORKDIR /opt/sonarqube

# Download SonarQube Community Edition
ARG SONARQUBE_VERSION=26.2.0.119303
RUN curl -fsSL "https://binaries.sonarsource.com/Distribution/sonarqube/sonarqube-${SONARQUBE_VERSION}.zip" \
    -o /tmp/sonarqube.zip \
    && unzip -q /tmp/sonarqube.zip -d /opt \
    && mv /opt/sonarqube-${SONARQUBE_VERSION}/* /opt/sonarqube/ \
    && rm /tmp/sonarqube.zip \
    && chown -R sonarqube:sonarqube /opt/sonarqube

# Create startup script
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
# Startup script v2 - PORT from docker-compose environment\n\
# Database configuration (Hop3 injects PG* vars)\n\
export PGHOST="${PGHOST:-localhost}"\n\
export PGPORT="${PGPORT:-5432}"\n\
export PGDATABASE="${PGDATABASE:-sonarqube}"\n\
export PGUSER="${PGUSER:-sonarqube}"\n\
export PGPASSWORD="${PGPASSWORD:-}"\n\
\n\
# SonarQube configuration\n\
export SONAR_WEB_PORT="${PORT:-8080}"\n\
export SONAR_DATA_DIR="${SONAR_DATA_DIR:-/var/lib/sonarqube/data}"\n\
export SONAR_EXTENSIONS_DIR="${SONAR_EXTENSIONS_DIR:-/var/lib/sonarqube/extensions}"\n\
export SONAR_LOGS_DIR="${SONAR_LOGS_DIR:-/var/lib/sonarqube/logs}"\n\
export SONAR_TEMP_DIR="${SONAR_TEMP_DIR:-/var/lib/sonarqube/temp}"\n\
\n\
# Write sonar.properties\n\
cat > /opt/sonarqube/conf/sonar.properties << EOF\n\
# Database\n\
sonar.jdbc.url=jdbc:postgresql://${PGHOST}:${PGPORT}/${PGDATABASE}\n\
sonar.jdbc.username=${PGUSER}\n\
sonar.jdbc.password=${PGPASSWORD}\n\
\n\
# Web Server\n\
sonar.web.host=0.0.0.0\n\
sonar.web.port=${SONAR_WEB_PORT}\n\
\n\
# Paths\n\
sonar.path.data=${SONAR_DATA_DIR}\n\
sonar.path.logs=${SONAR_LOGS_DIR}\n\
sonar.path.temp=${SONAR_TEMP_DIR}\n\
\n\
# Elasticsearch (embedded)\n\
sonar.search.javaAdditionalOpts=${SONAR_SEARCH_JAVAADDITIONALOPTS:--Dnode.store.allow_mmap=false}\n\
EOF\n\
\n\
# Ensure proper ownership\n\
chown -R sonarqube:sonarqube /var/lib/sonarqube /opt/sonarqube/conf\n\
\n\
# Run SonarQube as sonarqube user\n\
cd /opt/sonarqube\n\
exec su sonarqube -c "/opt/sonarqube/bin/linux-x86-64/sonar.sh console"\n\
' > /usr/local/bin/start-sonarqube.sh \
    && chmod +x /usr/local/bin/start-sonarqube.sh

# Environment (PORT is injected by Hop3, default 8080 is in startup script)
ENV SONAR_DATA_DIR=/var/lib/sonarqube/data
ENV SONAR_EXTENSIONS_DIR=/var/lib/sonarqube/extensions
ENV SONAR_LOGS_DIR=/var/lib/sonarqube/logs
ENV SONAR_TEMP_DIR=/var/lib/sonarqube/temp

# Data volumes
VOLUME /var/lib/sonarqube/data
VOLUME /var/lib/sonarqube/extensions
VOLUME /var/lib/sonarqube/logs

EXPOSE 8080

USER root
CMD ["/usr/local/bin/start-sonarqube.sh"]
