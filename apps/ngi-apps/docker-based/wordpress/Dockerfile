# WordPress Dockerfile for Hop3
# Uses Apache + mod_php for simplicity (single process web server)

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install Apache, PHP, and required extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    apache2 \
    libapache2-mod-php \
    php \
    php-mysql \
    php-curl \
    php-gd \
    php-intl \
    php-mbstring \
    php-xml \
    php-zip \
    php-imagick \
    unzip \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && a2enmod rewrite

# Create app directory
WORKDIR /var/www/html

# Download WordPress
ARG WORDPRESS_VERSION=6.4.2
RUN rm -f index.html \
    && curl -sL "https://wordpress.org/wordpress-${WORDPRESS_VERSION}.tar.gz" | tar xz --strip-components=1

# Copy Hop3 configuration
COPY wp-config-hop3.php wp-config.php

# Create required directories and set permissions
RUN mkdir -p wp-content/uploads \
    && chown -R www-data:www-data /var/www/html

# Configure Apache to listen on fixed port 8080 (Docker handles port mapping)
RUN echo 'Listen 8080' > /etc/apache2/ports.conf \
    && sed -i 's/<VirtualHost \*:80>/<VirtualHost *:8080>/' /etc/apache2/sites-available/000-default.conf \
    && echo 'ServerName localhost' >> /etc/apache2/apache2.conf

# Enable .htaccess
RUN sed -i '/<Directory \/var\/www\/>/,/<\/Directory>/ s/AllowOverride None/AllowOverride All/' /etc/apache2/apache2.conf

# Copy startup script
COPY start-wordpress.sh /usr/local/bin/start-wordpress.sh
RUN chmod +x /usr/local/bin/start-wordpress.sh

EXPOSE 8080

CMD ["/usr/local/bin/start-wordpress.sh"]
