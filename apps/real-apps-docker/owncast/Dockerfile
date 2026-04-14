# Owncast Dockerfile for Hop3
# Built from debian:trixie-slim + downloaded release zip.
# ffmpeg is a runtime dependency for transcoding livestreams.

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    curl \
    ca-certificates \
    unzip \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash owncast

WORKDIR /opt/owncast

ARG OWNCAST_VERSION=0.2.5
ARG TARGETARCH=64bit
RUN curl -fsSL \
    "https://github.com/owncast/owncast/releases/download/v${OWNCAST_VERSION}/owncast-${OWNCAST_VERSION}-linux-${TARGETARCH}.zip" \
    -o /tmp/owncast.zip \
    && unzip /tmp/owncast.zip -d /opt/owncast \
    && rm /tmp/owncast.zip \
    && chmod +x /opt/owncast/owncast

RUN mkdir -p /data && chown -R owncast:owncast /opt/owncast /data

COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

EXPOSE 8080 1935

CMD ["/usr/local/bin/start.sh"]
