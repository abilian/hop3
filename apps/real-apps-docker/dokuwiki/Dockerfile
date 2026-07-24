# DokuWiki Dockerfile for Hop3
# A simple, versatile wiki that doesn't require a database

FROM php:8.3-apache@sha256:a05f87f7f1e3927b9f3a44d64c01dfe15992328fa179bdfa72ad06e66769ff57

WORKDIR /var/www/html

# renovate: datasource=github-releases depName=dokuwiki/dokuwiki versioning=loose extractVersion=^release-(?<version>.+)$
ARG DOKUWIKI_VERSION=2024-02-06b

# Download and extract DokuWiki. Use HTTPS (plain HTTP was reset by the peer in
# CI) and fail loudly on a non-2xx so a bad fetch can't produce an empty extract.
RUN curl -fSL https://download.dokuwiki.org/src/dokuwiki/dokuwiki-${DOKUWIKI_VERSION}.tgz | tar -xz --strip-components 1 -f - && \
    rm -f install.php

# Enable Apache rewrite module
RUN a2enmod rewrite

# Set proper permissions
RUN chown -R www-data:www-data /var/www/html

# Configure Apache to allow .htaccess
RUN sed -i 's/AllowOverride None/AllowOverride All/g' /etc/apache2/apache2.conf

# Configure PHP
RUN echo "upload_max_filesize = 64M" >> /usr/local/etc/php/conf.d/dokuwiki.ini && \
    echo "post_max_size = 64M" >> /usr/local/etc/php/conf.d/dokuwiki.ini && \
    echo "memory_limit = 128M" >> /usr/local/etc/php/conf.d/dokuwiki.ini

# Install Python for startup script
RUN apt-get update && apt-get install -y --no-install-recommends python3 && rm -rf /var/lib/apt/lists/*

# Copy startup script
COPY start.py /start.py

EXPOSE 80

CMD ["python3", "/start.py"]
