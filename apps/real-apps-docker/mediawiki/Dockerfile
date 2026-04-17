# MediaWiki Dockerfile for Hop3
# Built from Debian base per the demo guideline — no FROM mediawiki.

FROM debian:trixie-slim

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
RUN set -eux; \
    MAJOR_MINOR="${MEDIAWIKI_VERSION%.*}"; \
    curl -fsSL "https://releases.wikimedia.org/mediawiki/${MAJOR_MINOR}/mediawiki-${MEDIAWIKI_VERSION}.tar.gz" \
      | tar xz --strip-components=1

RUN composer install --no-dev --optimize-autoloader --no-interaction

RUN chown -R mediawiki:mediawiki /var/www/mediawiki

COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

EXPOSE 8080

CMD ["/usr/local/bin/start.sh"]
