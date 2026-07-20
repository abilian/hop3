# GoToSocial Dockerfile for Hop3
# Built from debian:trixie-slim + downloaded release tarball

FROM debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash gotosocial

WORKDIR /opt/gotosocial

ARG GOTOSOCIAL_VERSION=0.21.2
ARG TARGETARCH=amd64
RUN curl -fsSL \
    "https://codeberg.org/superseriousbusiness/gotosocial/releases/download/v${GOTOSOCIAL_VERSION}/gotosocial_${GOTOSOCIAL_VERSION}_linux_${TARGETARCH}.tar.gz" \
    | tar xz -C /opt/gotosocial

RUN mkdir -p /data && chown gotosocial:gotosocial /data /opt/gotosocial

COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

EXPOSE 8080

CMD ["/usr/local/bin/start.sh"]
