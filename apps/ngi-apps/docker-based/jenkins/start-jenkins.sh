#!/bin/bash
set -e

# Required environment variables - fail fast if not set
: "${PORT:?ERROR: PORT is required}"

# Optional with defaults (non-critical)
export JENKINS_HOME="${JENKINS_HOME:-/var/jenkins_home}"
export JAVA_OPTS="${JAVA_OPTS:--Djava.awt.headless=true}"

# Build Jenkins options with the required port
JENKINS_OPTS="--httpPort=${PORT}"

# Ensure proper ownership
chown -R jenkins:jenkins /var/jenkins_home

# Run Jenkins as jenkins user
exec su jenkins -c "java ${JAVA_OPTS} -jar /usr/share/jenkins/jenkins.war ${JENKINS_OPTS}"
