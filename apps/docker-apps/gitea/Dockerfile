# Gitea Dockerfile for Hop3
# Self-hosted Git service

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies including envsubst
RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    git \
    git-lfs \
    curl \
    ca-certificates \
    gettext-base \
    && rm -rf /var/lib/apt/lists/*

# Create gitea user
RUN useradd -m -s /bin/bash gitea

# Create app directory
WORKDIR /home/gitea

# Download Gitea binary
ARG GITEA_VERSION=1.21.5
ARG TARGETARCH=amd64
RUN curl -sL "https://dl.gitea.com/gitea/${GITEA_VERSION}/gitea-${GITEA_VERSION}-linux-${TARGETARCH}" -o /usr/local/bin/gitea \
    && chmod +x /usr/local/bin/gitea

# Create required directories
RUN mkdir -p /home/gitea/custom/conf /home/gitea/data /home/gitea/repos /home/gitea/log \
    && chown -R gitea:gitea /home/gitea

# Copy config template
COPY --chown=gitea:gitea app.ini.template /home/gitea/custom/conf/app.ini.template

# Copy startup script
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Environment (PORT and PG* are required, no defaults)
ENV GITEA_WORK_DIR=/home/gitea
ENV GITEA_CUSTOM=/home/gitea/custom

EXPOSE 8080

USER root
CMD ["/usr/local/bin/start.sh"]
