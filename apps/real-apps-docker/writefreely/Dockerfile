# WriteFreely Dockerfile for Hop3
# Built from debian:trixie-slim + downloaded release tarball

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash writefreely

WORKDIR /opt/writefreely

ARG WRITEFREELY_VERSION=0.16.0
ARG TARGETARCH=amd64
RUN curl -fsSL \
    "https://github.com/writefreely/writefreely/releases/download/v${WRITEFREELY_VERSION}/writefreely_${WRITEFREELY_VERSION}_linux_${TARGETARCH}.tar.gz" \
    | tar xz -C /opt/writefreely --strip-components=1

RUN mkdir -p /data && chown -R writefreely:writefreely /opt/writefreely /data

COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

EXPOSE 8080

CMD ["/usr/local/bin/start.sh"]
