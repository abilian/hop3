# Gatus Dockerfile for Hop3
#
# Two-stage build: compile the Go binary in a golang image, then
# assemble a slim runtime image. Upstream ships no prebuilt binary,
# only Docker images; we build from source to avoid pulling an
# opaque image.

FROM golang:1-trixie@sha256:4ee9ffa999b4583ce281939cdff828763083610292f252279a0cee77473bd9a7 AS builder

ARG GATUS_VERSION=5.35.0
WORKDIR /build

RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL \
        "https://github.com/TwiN/gatus/archive/refs/tags/v${GATUS_VERSION}.tar.gz" \
        | tar xz --strip-components=1

RUN go build -ldflags="-s -w" -o /build/gatus .


FROM debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash gatus

WORKDIR /opt/gatus
COPY --from=builder /build/gatus /usr/local/bin/gatus
RUN mkdir -p /opt/gatus/config /data && chown -R gatus:gatus /opt/gatus /data

COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

EXPOSE 8080

CMD ["/usr/local/bin/start.sh"]
