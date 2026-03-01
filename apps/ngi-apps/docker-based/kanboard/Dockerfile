# Kanboard Dockerfile for Hop3
# Kanban project management

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install Apache, PHP, and MySQL extension
RUN apt-get update && apt-get install -y --no-install-recommends \
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

# Create config file
RUN echo '<?php\n\
// Kanboard configuration for Hop3\n\
\n\
// Database configuration from environment\n\
define("DB_DRIVER", "mysql");\n\
define("DB_HOST", getenv("MYSQL_HOST") ?: "localhost");\n\
define("DB_PORT", getenv("MYSQL_PORT") ?: "3306");\n\
define("DB_USERNAME", getenv("MYSQL_USER") ?: "kanboard");\n\
define("DB_PASSWORD", getenv("MYSQL_PASSWORD") ?: "");\n\
define("DB_NAME", getenv("MYSQL_DATABASE") ?: "kanboard");\n\
\n\
// Enable plugins\n\
define("PLUGIN_INSTALLER", true);\n\
' > /var/www/html/config.php

# Configure Apache
RUN echo 'Listen 8080' > /etc/apache2/ports.conf \
    && sed -i 's/<VirtualHost \*:80>/<VirtualHost *:8080>/' /etc/apache2/sites-available/000-default.conf \
    && echo 'ServerName localhost' >> /etc/apache2/apache2.conf

# Enable .htaccess
RUN sed -i '/<Directory \/var\/www\/>/,/<\/Directory>/ s/AllowOverride None/AllowOverride All/' /etc/apache2/apache2.conf

EXPOSE 8080

CMD ["apache2ctl", "-D", "FOREGROUND"]
