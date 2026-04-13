# Monica Dockerfile for Hop3
# Personal CRM

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install Apache, PHP and required extensions.
# NOTE: we do NOT install debian's nodejs/npm — trixie ships v20 which
# breaks Laravel Mix's old ProgressPlugin config. We pin Node 18 from
# NodeSource below instead.
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
    curl \
    ca-certificates \
    gnupg \
    unzip \
    && rm -rf /var/lib/apt/lists/* \
    && a2enmod rewrite

# Install Node 18 (required for Laravel Mix / webpack in Monica v4.x;
# Node 20+ rejects the old ProgressPlugin reporter/reporters options).
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -q -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Composer
RUN curl -sS https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer

WORKDIR /var/www/html

# Download Monica v4.x. Monica v4.x uses an old Laravel Mix that
# passes ``reporter``/``reporters`` options to webpack's
# ProgressPlugin — webpack 5 rejects these outright. Patch the
# installed Mix before running the build. (The patch is stable
# across Mix 6.x; it removes the unrecognised options only.)
ARG MONICA_VERSION=v4.1.2
RUN rm -rf /var/www/html/* \
    && curl -sL "https://github.com/monicahq/monica/archive/refs/tags/${MONICA_VERSION}.tar.gz" | tar xz --strip-components=1 \
    && composer install --no-dev --no-interaction --prefer-dist --ignore-platform-reqs \
    && npm install --ignore-scripts \
    # Strip the webpack5-incompatible options from Laravel Mix's
    # ProgressPlugin config. sed pattern matches the lines
    # ``reporter: ...`` and ``reporters: ...`` inside the
    # ProgressPlugin() constructor argument.
    && find node_modules/laravel-mix -name "*.js" \
        -exec sed -i -E '/^\s*reporter[s]?\s*:/d' {} + \
    && NODE_OPTIONS=--openssl-legacy-provider npm run production \
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
