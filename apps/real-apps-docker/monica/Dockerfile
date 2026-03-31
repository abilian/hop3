# Monica Dockerfile for Hop3
# Personal CRM

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install Apache, PHP, Node.js and required extensions
RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    apache2 \
    libapache2-mod-php \
    php \
    php-mysql \
    php-gd \
    php-mbstring \
    php-xml \
    php-curl \
    php-zip \
    php-bcmath \
    php-intl \
    php-redis \
    nodejs \
    npm \
    curl \
    ca-certificates \
    unzip \
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

# Copy startup script
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

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

CMD ["/usr/local/bin/start.sh"]
