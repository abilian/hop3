# Kanboard Dockerfile for Hop3
# Kanban project management

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install Apache, PHP, and MySQL extension
RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    apache2 \
    libapache2-mod-php \
    php \
    php-mysql \
    php-pgsql \
    php-gd \
    php-mbstring \
    php-xml \
    php-zip \
    php-curl \
    php-ldap \
    curl \
    ca-certificates \
    unzip \
    && rm -rf /var/lib/apt/lists/* \
    && a2enmod rewrite

WORKDIR /var/www/html

# Download Kanboard
ARG KANBOARD_VERSION=1.2.37
RUN rm -f index.html \
    && curl -sL "https://github.com/kanboard/kanboard/archive/refs/tags/v${KANBOARD_VERSION}.tar.gz" | tar xz --strip-components=1 \
    && chown -R www-data:www-data /var/www/html

# Copy config file (uses getenv() to read env vars at runtime).
# COPY lands as root:root with the source's mode; the recursive chown
# above runs *before* this COPY, so we re-chown the file explicitly.
# Without this, kanboard's app/common.php require fails with
# "Permission denied" when Apache (running as www-data) reads the
# config — the symptom we hit on the first deploy attempt.
COPY config.php.template /var/www/html/config.php
RUN chown www-data:www-data /var/www/html/config.php \
    && chmod 640 /var/www/html/config.php

# Configure Apache
RUN echo 'Listen 8080' > /etc/apache2/ports.conf \
    && sed -i 's/<VirtualHost \*:80>/<VirtualHost *:8080>/' /etc/apache2/sites-available/000-default.conf \
    && echo 'ServerName localhost' >> /etc/apache2/apache2.conf

# Enable .htaccess
RUN sed -i '/<Directory \/var\/www\/>/,/<\/Directory>/ s/AllowOverride None/AllowOverride All/' /etc/apache2/apache2.conf

# Redirect Apache + PHP logs to the container's stdout/stderr. This is
# the 12-factor logs convention and — more concretely — the only path
# ``docker logs`` (and therefore Hop3's failure diagnostics) will see.
# Without this, kanboard 500s arrive in /var/log/apache2/error.log
# inside the container and never surface in failed-deploy logs.
RUN ln -sf /dev/stdout /var/log/apache2/access.log \
    && ln -sf /dev/stderr /var/log/apache2/error.log

# Copy startup script
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

EXPOSE 8080

CMD ["/usr/local/bin/start.sh"]
