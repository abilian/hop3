# Monica Dockerfile for Hop3
# Personal CRM

FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install Apache, PHP, Node.js and required extensions
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
    php8.2-bcmath \
    php8.2-intl \
    php8.2-redis \
    curl \
    ca-certificates \
    gnupg \
    unzip \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_18.x nodistro main" > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && a2enmod rewrite

# Install Composer
RUN curl -sS https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer

WORKDIR /var/www/html

# Download Monica v4.x (new architecture)
ARG MONICA_VERSION=v4.0.0
RUN rm -rf /var/www/html/* \
    && curl -sL "https://github.com/monicahq/monica/archive/refs/tags/${MONICA_VERSION}.tar.gz" | tar xz --strip-components=1 \
    && composer install --no-dev --no-interaction --prefer-dist --ignore-platform-reqs \
    && npm install --ignore-scripts \
    && npm run production \
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
APP_KEY=${APP_KEY:-base64:$(head -c 32 /dev/urandom | base64)}\n\
APP_URL=${APP_URL:-http://localhost:8080}\n\
APP_DEBUG=${APP_DEBUG:-false}\n\
APP_ENV=production\n\
\n\
DB_CONNECTION=mysql\n\
DB_HOST=${MYSQL_HOST:-localhost}\n\
DB_PORT=${MYSQL_PORT:-3306}\n\
DB_DATABASE=${MYSQL_DATABASE:-monica}\n\
DB_USERNAME=${MYSQL_USER:-monica}\n\
DB_PASSWORD=${MYSQL_PASSWORD}\n\
\n\
CACHE_DRIVER=file\n\
SESSION_DRIVER=file\n\
QUEUE_CONNECTION=sync\n\
\n\
MAIL_MAILER=log\n\
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
' > /usr/local/bin/start-monica.sh \
    && chmod +x /usr/local/bin/start-monica.sh

# Configure Apache
RUN echo 'Listen 8080' > /etc/apache2/ports.conf \
    && cat > /etc/apache2/sites-available/000-default.conf << 'VHOST'
<VirtualHost *:8080>
    DocumentRoot /var/www/html/public
    <Directory /var/www/html/public>
        AllowOverride All
        Require all granted
    </Directory>
</VirtualHost>
VHOST
RUN echo 'ServerName localhost' >> /etc/apache2/apache2.conf

EXPOSE 8080

CMD ["/usr/local/bin/start-monica.sh"]
