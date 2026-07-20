# SonarQube Dockerfile for Hop3
# Code quality and security analysis platform

# Use Debian Trixie (13) which has Java 21 in repositories
FROM debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies (procps needed for ps command used by SonarQube startup)
# SonarQube 26.x requires Java 21
RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
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

# Copy startup script
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Environment (PORT and PG* are required, no defaults)

# Data volumes
VOLUME /var/lib/sonarqube/data
VOLUME /var/lib/sonarqube/extensions
VOLUME /var/lib/sonarqube/logs

EXPOSE 8080

USER root
CMD ["/usr/local/bin/start.sh"]
