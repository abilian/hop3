# Jenkins Dockerfile for Hop3
# The leading open source automation server

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-21-jre-headless \
    curl \
    ca-certificates \
    git \
    openssh-client \
    fontconfig \
    libharfbuzz0b \
    libfreetype6 \
    && rm -rf /var/lib/apt/lists/*

# Create jenkins user
RUN useradd -m -d /var/jenkins_home -s /bin/bash jenkins

# Create directories
RUN mkdir -p /var/jenkins_home /usr/share/jenkins \
    && chown -R jenkins:jenkins /var/jenkins_home

# Download Jenkins WAR
ARG JENKINS_VERSION=2.440.3
RUN curl -fsSL "https://get.jenkins.io/war-stable/${JENKINS_VERSION}/jenkins.war" \
    -o /usr/share/jenkins/jenkins.war

# Create startup script
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
# Jenkins configuration\n\
export JENKINS_HOME="${JENKINS_HOME:-/var/jenkins_home}"\n\
export JENKINS_PORT="${PORT:-8080}"\n\
export JAVA_OPTS="${JAVA_OPTS:--Djava.awt.headless=true}"\n\
export JENKINS_OPTS="${JENKINS_OPTS:---httpPort=${JENKINS_PORT}}"\n\
\n\
# Ensure proper ownership\n\
chown -R jenkins:jenkins /var/jenkins_home\n\
\n\
# Run Jenkins as jenkins user\n\
exec su jenkins -c "java ${JAVA_OPTS} -jar /usr/share/jenkins/jenkins.war ${JENKINS_OPTS}"\n\
' > /usr/local/bin/start-jenkins.sh \
    && chmod +x /usr/local/bin/start-jenkins.sh

# Environment
ENV JENKINS_HOME=/var/jenkins_home
ENV PORT=8080

# Data volume
VOLUME /var/jenkins_home

EXPOSE 8080

USER root
CMD ["/usr/local/bin/start-jenkins.sh"]
