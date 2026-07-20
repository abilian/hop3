# Forgejo Dockerfile for Hop3
# Self-hosted Git service — community fork of Gitea

FROM debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    git \
    git-lfs \
    curl \
    ca-certificates \
    gettext-base \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash forgejo

WORKDIR /home/forgejo

ARG FORGEJO_VERSION=14.0.3
ARG TARGETARCH=amd64
RUN curl -fsSL "https://codeberg.org/forgejo/forgejo/releases/download/v${FORGEJO_VERSION}/forgejo-${FORGEJO_VERSION}-linux-${TARGETARCH}" -o /usr/local/bin/forgejo \
    && chmod +x /usr/local/bin/forgejo

RUN mkdir -p /home/forgejo/custom/conf /home/forgejo/data /home/forgejo/repos /home/forgejo/log \
    && chown -R forgejo:forgejo /home/forgejo

COPY --chown=forgejo:forgejo app.ini.template /home/forgejo/custom/conf/app.ini.template

COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

ENV GITEA_WORK_DIR=/home/forgejo
ENV GITEA_CUSTOM=/home/forgejo/custom

EXPOSE 8080

USER root
CMD ["/usr/local/bin/start.sh"]
