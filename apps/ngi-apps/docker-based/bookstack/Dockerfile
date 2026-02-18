# BookStack Dockerfile for Hop3
# Self-hosted wiki platform

FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install Apache, PHP, and required extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    apache2 \
    libapache2-mod-php8.2 \
    php8.2 \
    php8.2-mysql \
    php8.2-gd \
    php8.2-mbstring \
    php8.2-xml \
    php8.2-curl \
    php8.2-zip \
    php8.2-ldap \
    php8.2-intl \
    php8.2-tokenizer \
    curl \
    ca-certificates \
    unzip \
    && rm -rf /var/lib/apt/lists/* \
    && a2enmod rewrite

# Install Composer
RUN curl -sS https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer

WORKDIR /var/www/html

# Download BookStack
ARG BOOKSTACK_VERSION=v24.02.3
RUN rm -rf /var/www/html/* \
    && curl -sL "https://github.com/BookStackApp/BookStack/archive/refs/tags/${BOOKSTACK_VERSION}.tar.gz" | tar xz --strip-components=1 \
    && composer install --no-dev --no-interaction --prefer-dist \
    && chown -R www-data:www-data /var/www/html

# Create .env file from environment
RUN echo '#!/bin/bash\n\
# Generate .env file from environment variables\n\
cat > /var/www/html/.env << EOF\n\
APP_KEY=${APP_KEY:-base64:$(head -c 32 /dev/urandom | base64)}\n\
APP_URL=${APP_URL:-http://localhost:8080}\n\
APP_DEBUG=${APP_DEBUG:-false}\n\
\n\
DB_HOST=${MYSQL_HOST:-localhost}\n\
DB_PORT=${MYSQL_PORT:-3306}\n\
DB_DATABASE=${MYSQL_DATABASE:-bookstack}\n\
DB_USERNAME=${MYSQL_USER:-bookstack}\n\
DB_PASSWORD=${MYSQL_PASSWORD}\n\
\n\
CACHE_DRIVER=file\n\
SESSION_DRIVER=file\n\
QUEUE_CONNECTION=sync\n\
EOF\n\
\n\
# Run migrations\n\
cd /var/www/html && php artisan migrate --force\n\
\n\
# Start Apache\n\
exec apache2ctl -D FOREGROUND\n\
' > /usr/local/bin/start-bookstack.sh \
    && chmod +x /usr/local/bin/start-bookstack.sh

# Configure Apache
RUN echo 'Listen 8080' > /etc/apache2/ports.conf \
    && printf '<VirtualHost *:8080>\n    DocumentRoot /var/www/html/public\n    <Directory /var/www/html/public>\n        AllowOverride All\n        Require all granted\n    </Directory>\n</VirtualHost>\n' > /etc/apache2/sites-available/000-default.conf \
    && echo 'ServerName localhost' >> /etc/apache2/apache2.conf

EXPOSE 8080

CMD ["/usr/local/bin/start-bookstack.sh"]
