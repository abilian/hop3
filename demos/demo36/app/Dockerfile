# Demo 36: Kanboard
# Self-hosted Kanban project management
# https://kanboard.org/
# Built from source on debian:bookworm-slim

FROM debian:bookworm-slim

# Install nginx, PHP, and dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        nginx \
        php-fpm \
        php-mysql \
        php-pgsql \
        php-sqlite3 \
        php-gd \
        php-mbstring \
        php-xml \
        php-zip \
        php-curl \
        php-ldap \
        curl \
        ca-certificates \
        supervisor \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /run/php

# Kanboard version
ARG KANBOARD_VERSION=1.2.48

# Download and extract Kanboard
WORKDIR /var/www
RUN curl -fsSL "https://github.com/kanboard/kanboard/archive/refs/tags/v${KANBOARD_VERSION}.tar.gz" | \
    tar -xz && \
    mv kanboard-${KANBOARD_VERSION} kanboard && \
    chown -R www-data:www-data /var/www/kanboard && \
    chmod -R 755 /var/www/kanboard/data /var/www/kanboard/plugins

# Configure nginx
RUN rm /etc/nginx/sites-enabled/default
COPY nginx.conf /etc/nginx/sites-enabled/kanboard.conf

# Configure PHP-FPM to listen on socket
RUN sed -i 's|listen = /run/php/php.*-fpm.sock|listen = /run/php/php-fpm.sock|' /etc/php/*/fpm/pool.d/www.conf

# Configure supervisor
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Copy startup script
COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 80

CMD ["/start.sh"]
