# MediaWiki Dockerfile for Hop3
# Built from Debian base per the demo guideline — no FROM mediawiki.

FROM debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    php-cli \
    php-curl \
    php-pgsql \
    php-mbstring \
    php-xml \
    php-intl \
    php-zip \
    php-gd \
    php-apcu \
    php-fpm \
    composer \
    curl \
    ca-certificates \
    imagemagick \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash mediawiki

ARG MEDIAWIKI_VERSION=1.41.2
WORKDIR /var/www/mediawiki

# Major.minor release feed directory — 1.41.2 → 1.41/
# Download to a file, don't `curl | tar`: releases.wikimedia.org resets the
# HTTP/2 stream mid-transfer (curl 92 "stream not closed cleanly"), and piping
# feeds the truncated bytes into tar → "Error is not recoverable". --http1.1
# avoids the HTTP/2 cancel; --retry rides out a transient reset; extracting from
# the finished file means a bad fetch fails loudly at curl, never as a corrupt
# archive that looks like a build-logic error.
RUN set -eux; \
    MAJOR_MINOR="${MEDIAWIKI_VERSION%.*}"; \
    curl -fSL --http1.1 --retry 5 --retry-delay 3 --retry-all-errors \
      -o mediawiki.tar.gz \
      "https://releases.wikimedia.org/mediawiki/${MAJOR_MINOR}/mediawiki-${MEDIAWIKI_VERSION}.tar.gz"; \
    tar -xzf mediawiki.tar.gz --strip-components=1; \
    rm mediawiki.tar.gz

RUN composer install --no-dev --optimize-autoloader --no-interaction

RUN chown -R mediawiki:mediawiki /var/www/mediawiki

COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

EXPOSE 8080

CMD ["/usr/local/bin/start.sh"]
