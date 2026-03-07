# Jenkins Dockerfile for Hop3
# The leading open source automation server

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
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

# Copy startup script
COPY start-jenkins.sh /usr/local/bin/start-jenkins.sh
RUN chmod +x /usr/local/bin/start-jenkins.sh

# Environment (PORT is required, no default)
ENV JENKINS_HOME=/var/jenkins_home

# Data volume
VOLUME /var/jenkins_home

EXPOSE 8080

USER root
CMD ["/usr/local/bin/start-jenkins.sh"]
