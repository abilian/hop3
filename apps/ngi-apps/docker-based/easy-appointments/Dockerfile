# Easy!Appointments Dockerfile for Hop3
# Open source appointment scheduling

FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install Apache, PHP, and required extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    apache2 \
    libapache2-mod-php8.2 \
    php8.2 \
    php8.2-mysql \
    php8.2-mbstring \
    php8.2-curl \
    php8.2-xml \
    php8.2-gd \
    curl \
    ca-certificates \
    unzip \
    && rm -rf /var/lib/apt/lists/* \
    && a2enmod rewrite

WORKDIR /var/www/html

# Download Easy!Appointments
ARG EA_VERSION=1.5.0
RUN rm -rf /var/www/html/* \
    && curl -sL "https://github.com/alextselegidis/easyappointments/releases/download/${EA_VERSION}/easyappointments-${EA_VERSION}.zip" -o ea.zip \
    && unzip ea.zip \
    && rm ea.zip \
    && chown -R www-data:www-data /var/www/html

# Create startup script
RUN printf '%s\n' '#!/bin/bash' \
    'set -e' \
    '' \
    'cd /var/www/html' \
    '' \
    '# Create config.php from environment variables (shell expands vars)' \
    'cat > config.php << EOFPHP' \
    '<?php' \
    'class Config {' \
    '    const BASE_URL = "${APP_URL:-http://localhost:8080}";' \
    '    const LANGUAGE = "english";' \
    '    const DEBUG_MODE = false;' \
    '' \
    '    const DB_HOST = "${MYSQL_HOST:-localhost}";' \
    '    const DB_NAME = "${MYSQL_DATABASE:-easyappointments}";' \
    '    const DB_USERNAME = "${MYSQL_USER:-easyappointments}";' \
    '    const DB_PASSWORD = "${MYSQL_PASSWORD:-}";' \
    '' \
    '    const GOOGLE_SYNC_FEATURE = false;' \
    '    const GOOGLE_CLIENT_ID = "";' \
    '    const GOOGLE_CLIENT_SECRET = "";' \
    '}' \
    'EOFPHP' \
    '' \
    'chown www-data:www-data config.php' \
    '' \
    '# Ensure storage is writable' \
    'chown -R www-data:www-data storage' \
    'chmod -R 755 storage' \
    '' \
    '# Start Apache' \
    'exec apache2ctl -D FOREGROUND' \
    > /usr/local/bin/start-easyappointments.sh \
    && chmod +x /usr/local/bin/start-easyappointments.sh

# Configure Apache
RUN echo 'Listen 8080' > /etc/apache2/ports.conf \
    && printf '<VirtualHost *:8080>\n    DocumentRoot /var/www/html\n    <Directory /var/www/html>\n        AllowOverride All\n        Require all granted\n    </Directory>\n</VirtualHost>\n' > /etc/apache2/sites-available/000-default.conf
RUN echo 'ServerName localhost' >> /etc/apache2/apache2.conf

EXPOSE 8080

CMD ["/usr/local/bin/start-easyappointments.sh"]
