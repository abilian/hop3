# Invoice Ninja Dockerfile for Hop3
# Open source invoicing platform

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install Apache, PHP, and required extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    apache2 \
    libapache2-mod-php \
    php \
    php-mysql \
    php-pgsql \
    php-gd \
    php-mbstring \
    php-xml \
    php-curl \
    php-zip \
    php-bcmath \
    php-gmp \
    php-intl \
    php-redis \
    curl \
    ca-certificates \
    unzip \
    default-mysql-client \
    && rm -rf /var/lib/apt/lists/* \
    && a2enmod rewrite

# Install Composer
RUN curl -sS https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer

WORKDIR /var/www/html

# Download Invoice Ninja
ARG INVOICENINJA_VERSION=5.12.64
RUN rm -rf /var/www/html/* \
    && curl -sL "https://github.com/invoiceninja/invoiceninja/archive/refs/tags/v${INVOICENINJA_VERSION}.tar.gz" | tar xz --strip-components=1 \
    && composer install --no-dev --no-interaction --prefer-dist --ignore-platform-reqs \
    && mkdir -p storage/framework/{sessions,views,cache} \
    && mkdir -p storage/logs \
    && mkdir -p bootstrap/cache \
    && chown -R www-data:www-data /var/www/html

# Create startup script
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
cd /var/www/html\n\
\n\
# Generate .env file from environment variables\n\
cat > .env << EOF\n\
APP_NAME="Invoice Ninja"\n\
APP_KEY=${APP_KEY:-base64:$(head -c 32 /dev/urandom | base64)}\n\
APP_URL=${APP_URL:-http://localhost:8080}\n\
APP_DEBUG=${APP_DEBUG:-false}\n\
APP_ENV=production\n\
\n\
DB_CONNECTION=mysql\n\
DB_HOST=${MYSQL_HOST:-localhost}\n\
DB_PORT=${MYSQL_PORT:-3306}\n\
DB_DATABASE=${MYSQL_DATABASE:-invoiceninja}\n\
DB_USERNAME=${MYSQL_USER:-invoiceninja}\n\
DB_PASSWORD=${MYSQL_PASSWORD}\n\
\n\
CACHE_DRIVER=file\n\
SESSION_DRIVER=file\n\
QUEUE_CONNECTION=sync\n\
\n\
MAIL_MAILER=log\n\
\n\
NINJA_ENVIRONMENT=selfhost\n\
TRUSTED_PROXIES=*\n\
EOF\n\
\n\
chown www-data:www-data .env\n\
\n\
# Ensure storage directories exist and are writable\n\
mkdir -p storage/framework/{sessions,views,cache}\n\
mkdir -p storage/logs\n\
mkdir -p bootstrap/cache\n\
chown -R www-data:www-data storage bootstrap/cache\n\
chmod -R 775 storage bootstrap/cache\n\
\n\
# Create storage link if not exists\n\
if [ ! -L public/storage ]; then\n\
    php artisan storage:link\n\
fi\n\
\n\
# Clear and cache config\n\
php artisan config:clear\n\
php artisan cache:clear\n\
\n\
# Run migrations\n\
php artisan migrate --force\n\
\n\
# Start Apache\n\
exec apache2ctl -D FOREGROUND\n\
' > /usr/local/bin/start-invoiceninja.sh \
    && chmod +x /usr/local/bin/start-invoiceninja.sh

# Configure Apache
RUN echo 'Listen 8080' > /etc/apache2/ports.conf \
    && printf '<VirtualHost *:8080>\n    DocumentRoot /var/www/html/public\n    <Directory /var/www/html/public>\n        AllowOverride All\n        Require all granted\n    </Directory>\n</VirtualHost>\n' > /etc/apache2/sites-available/000-default.conf
RUN echo 'ServerName localhost' >> /etc/apache2/apache2.conf

EXPOSE 8080

CMD ["/usr/local/bin/start-invoiceninja.sh"]
