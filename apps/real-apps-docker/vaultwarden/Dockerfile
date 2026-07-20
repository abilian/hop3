# Vaultwarden Dockerfile for Hop3
#
# Two-stage build:
#   1. Compile the vaultwarden binary from source with the Rust toolchain.
#   2. Assemble a slim runtime image with the binary + downloaded web-vault
#      static assets from dani-garcia/bw_web_builds.
#
# Upstream Vaultwarden ships only Docker images (no prebuilt binaries),
# and we avoid pulling third-party images per the project's Docker
# guidelines — so we compile.

FROM rust:1-trixie@sha256:9a2cd304a852f05d3352f75bc2775242371c0169a72dbb40d5d881379d571989 AS builder

ARG VAULTWARDEN_VERSION=1.35.4

RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    pkg-config \
    libssl-dev \
    libmariadb-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
RUN curl -fsSL "https://github.com/dani-garcia/vaultwarden/archive/refs/tags/${VAULTWARDEN_VERSION}.tar.gz" \
    | tar xz --strip-components=1

# MySQL + Postgres + SQLite support; matches upstream Docker feature set.
RUN cargo build --features "sqlite,mysql,postgresql" --release


FROM debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    curl \
    ca-certificates \
    openssl \
    libmariadb-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash vaultwarden

ARG WEBVAULT_VERSION=v2025.1.1
RUN mkdir -p /opt/web-vault && \
    curl -fsSL \
    "https://github.com/dani-garcia/bw_web_builds/releases/download/${WEBVAULT_VERSION}/bw_web_${WEBVAULT_VERSION}.tar.gz" \
    | tar xz -C /opt/web-vault --strip-components=1

COPY --from=builder /build/target/release/vaultwarden /usr/local/bin/vaultwarden

COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

EXPOSE 8080

CMD ["/usr/local/bin/start.sh"]
