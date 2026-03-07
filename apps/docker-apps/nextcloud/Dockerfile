# Nextcloud Dockerfile for Hop3
# Uses Apache + mod_php for simplicity

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install Apache, PHP, and required extensions for Nextcloud
RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    apache2 \
    libapache2-mod-php \
    php \
    php-pgsql \
    php-mysql \
    php-curl \
    php-gd \
    php-intl \
    php-mbstring \
    php-xml \
    php-zip \
    php-bz2 \
    php-gmp \
    php-bcmath \
    php-imagick \
    php-redis \
    php-apcu \
    unzip \
    bzip2 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && a2enmod rewrite headers env dir mime

# Create app directory
WORKDIR /var/www/html

# Download Nextcloud (31.x required for PHP 8.4 support)
ARG NEXTCLOUD_VERSION=31.0.0
RUN rm -f index.html \
    && curl -sL "https://download.nextcloud.com/server/releases/nextcloud-${NEXTCLOUD_VERSION}.tar.bz2" | tar xj --strip-components=1

# Copy Hop3 configuration files
COPY config-hop3.php config/config.php
COPY autoconfig-hop3.php config/autoconfig.php

# Create required directories and set permissions
RUN mkdir -p data config \
    && chown -R www-data:www-data /var/www/html

# Configure Apache to listen on fixed port 8080 (Docker handles port mapping)
RUN echo 'Listen 8080' > /etc/apache2/ports.conf \
    && sed -i 's/<VirtualHost \*:80>/<VirtualHost *:8080>/' /etc/apache2/sites-available/000-default.conf \
    && echo 'ServerName localhost' >> /etc/apache2/apache2.conf

# Enable .htaccess and increase upload limits
RUN sed -i '/<Directory \/var\/www\/>/,/<\/Directory>/ s/AllowOverride None/AllowOverride All/' /etc/apache2/apache2.conf

# PHP configuration for large files
RUN echo 'memory_limit = 512M' > /etc/php/8.4/apache2/conf.d/99-nextcloud.ini \
    && echo 'upload_max_filesize = 16G' >> /etc/php/8.4/apache2/conf.d/99-nextcloud.ini \
    && echo 'post_max_size = 16G' >> /etc/php/8.4/apache2/conf.d/99-nextcloud.ini \
    && echo 'max_execution_time = 3600' >> /etc/php/8.4/apache2/conf.d/99-nextcloud.ini \
    && echo 'max_input_time = 3600' >> /etc/php/8.4/apache2/conf.d/99-nextcloud.ini

# Copy startup script
COPY start-nextcloud.sh /usr/local/bin/start-nextcloud.sh
RUN chmod +x /usr/local/bin/start-nextcloud.sh

EXPOSE 8080

CMD ["/usr/local/bin/start-nextcloud.sh"]
