# Keycloak Dockerfile for Hop3
# Enterprise SSO / OIDC / SAML identity provider
#
# Built from debian:trixie-slim per Hop3 convention (CLAUDE.md →
# "Never use official Docker images in demos") so we exercise real
# deployment plumbing rather than trusting upstream's image recipe.
#
# Writable $KC_HOME_DIR is the key difference vs the nix-gen variant:
# here /opt/keycloak is a regular directory we own, so kc.sh's
# implicit `build` step (Quarkus augmentation) can freely write
# generated-bytecode.jar + data/ without the read-only-nix-store
# blocker tracked in DEFERRED-APPS.md #12.

FROM debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd

ENV DEBIAN_FRONTEND=noninteractive

# Keycloak 26 requires Java 21. Debian trixie ships openjdk-21 in main;
# no third-party apt repo dance needed. curl for downloading the
# Keycloak tarball, tar/gzip to extract it, ca-certificates for TLS.
RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
        ca-certificates \
        curl \
        openjdk-21-jre-headless \
        tar \
        gzip \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64

RUN useradd -m -s /bin/bash keycloak

ARG KEYCLOAK_VERSION=26.1.4
RUN curl -fsSL "https://github.com/keycloak/keycloak/releases/download/${KEYCLOAK_VERSION}/keycloak-${KEYCLOAK_VERSION}.tar.gz" \
      -o /tmp/keycloak.tar.gz \
    && tar -xzf /tmp/keycloak.tar.gz -C /opt \
    && mv "/opt/keycloak-${KEYCLOAK_VERSION}" /opt/keycloak \
    && rm /tmp/keycloak.tar.gz \
    && chown -R keycloak:keycloak /opt/keycloak

ENV KC_HOME_DIR=/opt/keycloak
ENV PATH=/opt/keycloak/bin:${PATH}

# Copy the entry script as root so we can set ownership + exec bits,
# then drop to the keycloak user for runtime.
COPY start.sh /usr/local/bin/start.sh
RUN chmod 0755 /usr/local/bin/start.sh

USER keycloak
WORKDIR /opt/keycloak

# No EXPOSE: Hop3 assigns the host port dynamically and injects PORT.
# The container listens on whatever PORT env var it's given.

ENTRYPOINT ["/usr/local/bin/start.sh"]
