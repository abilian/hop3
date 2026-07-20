# Paheko Dockerfile for Hop3
# Nonprofit accounting & association management (SQLite).

FROM debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    apache2 \
    libapache2-mod-php \
    php \
    php-sqlite3 \
    php-gd \
    php-mbstring \
    php-xml \
    php-zip \
    php-curl \
    php-intl \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN a2enmod rewrite && echo "ServerName localhost" >> /etc/apache2/apache2.conf

ARG PAHEKO_VERSION=1.3.15
# Paheko's canonical fossil mirror has bot-verification; use the
# github mirror to fetch via codeload.
RUN curl -fsSL "https://codeload.github.com/paheko/paheko/tar.gz/refs/tags/${PAHEKO_VERSION}" \
    | tar xz -C /var/www/ && mv /var/www/paheko-${PAHEKO_VERSION} /var/www/paheko

# Paheko writes SQLite + uploads under a DATA_ROOT which defaults to
# the checkout itself; point it at a persistent volume.
RUN mkdir -p /data && chown -R www-data:www-data /var/www/paheko /data

COPY apache.conf /etc/apache2/sites-available/000-default.conf
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

EXPOSE 80

CMD ["/usr/local/bin/start.sh"]
