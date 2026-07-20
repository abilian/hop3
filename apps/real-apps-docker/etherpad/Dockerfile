# Etherpad Dockerfile for Hop3
# Real-time collaborative editor

FROM debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd

ENV DEBIAN_FRONTEND=noninteractive
ENV NODE_ENV=production

# Install Node.js and dependencies.
# NOTE: We install pnpm via ``npm install -g`` instead of ``corepack
# enable``. Debian Trixie ships a Node.js 20.x patch whose pairing
# with the bundled corepack trips ERR_VM_DYNAMIC_IMPORT_CALLBACK_MISSING
# when corepack invokes pnpm. Going around corepack avoids the shim
# layer entirely; pnpm on PATH is what bin/installDeps.sh actually needs.
RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    nodejs \
    npm \
    curl \
    ca-certificates \
    python3 \
    && npm install -g pnpm@8 \
    && rm -rf /var/lib/apt/lists/*

# Create etherpad user
RUN useradd -m -s /bin/bash etherpad

WORKDIR /home/etherpad/app

# Download Etherpad and install dependencies.
# NOTE: do not pin much below 2.2.x. Etherpad 2.0.3 imports ueberdb2 in
# the CommonJS-default style, but the ueberdb2 published on npm has
# since switched to ESM-style named exports — at install time pnpm
# resolves the new ueberdb2 and the old import breaks at startup with
# ``ueberdb2.default.Database is not a constructor``.
ARG ETHERPAD_VERSION=2.7.2
ENV CI=true
RUN curl -sL "https://github.com/ether/etherpad-lite/archive/refs/tags/v${ETHERPAD_VERSION}.tar.gz" | tar xz --strip-components=1 \
    && bin/installDeps.sh \
    && chown -R etherpad:etherpad /home/etherpad

# Copy startup script
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Environment (PORT is required, no default)
EXPOSE 8080

CMD ["/usr/local/bin/start.sh"]
