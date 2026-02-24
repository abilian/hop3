# WordPress Dockerfile for Hop3
# Uses Apache + mod_php for simplicity (single process web server)

FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install Apache, PHP, and required extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    apache2 \
    libapache2-mod-php8.2 \
    php8.2 \
    php8.2-mysql \
    php8.2-curl \
    php8.2-gd \
    php8.2-intl \
    php8.2-mbstring \
    php8.2-xml \
    php8.2-zip \
    php8.2-imagick \
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

# Expose default port
EXPOSE 8080

# Start Apache in foreground
CMD ["apache2ctl", "-D", "FOREGROUND"]
