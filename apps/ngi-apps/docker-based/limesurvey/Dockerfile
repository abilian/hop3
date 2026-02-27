# LimeSurvey Dockerfile for Hop3
# Professional online survey tool

FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install Apache, PHP, and dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    apache2 \
    libapache2-mod-php \
    php \
    php-pgsql \
    php-mysql \
    php-gd \
    php-mbstring \
    php-xml \
    php-zip \
    php-ldap \
    php-imap \
    php-curl \
    php-intl \
    curl \
    ca-certificates \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Configure Apache
RUN a2enmod rewrite \
    && echo "ServerName localhost" >> /etc/apache2/apache2.conf

# Create directories
RUN mkdir -p /var/www/limesurvey /var/lib/limesurvey/upload \
    && chown -R www-data:www-data /var/www/limesurvey /var/lib/limesurvey

WORKDIR /var/www/limesurvey

# Download LimeSurvey from official download server
ARG LIMESURVEY_VERSION=6.16.10+260223
RUN curl -fsSL "https://download.limesurvey.org/latest-master/limesurvey${LIMESURVEY_VERSION}.zip" \
    -o /tmp/limesurvey.zip \
    && unzip -q /tmp/limesurvey.zip -d /tmp \
    && mv /tmp/limesurvey/* /var/www/limesurvey/ \
    && rm -rf /tmp/limesurvey.zip /tmp/limesurvey \
    && chown -R www-data:www-data /var/www/limesurvey

# Configure Apache virtual host
RUN printf '%s\n' \
    '<VirtualHost *:8080>' \
    '    DocumentRoot /var/www/limesurvey' \
    '    <Directory /var/www/limesurvey>' \
    '        AllowOverride All' \
    '        Require all granted' \
    '    </Directory>' \
    '    ErrorLog ${APACHE_LOG_DIR}/error.log' \
    '    CustomLog ${APACHE_LOG_DIR}/access.log combined' \
    '</VirtualHost>' \
    > /etc/apache2/sites-available/limesurvey.conf \
    && a2dissite 000-default \
    && a2ensite limesurvey \
    && sed -i 's/Listen 80/Listen 8080/' /etc/apache2/ports.conf

# Create startup script
RUN printf '%s\n' '#!/bin/bash' \
    'set -e' \
    '' \
    '# Database configuration (Hop3 injects PG* vars)' \
    'PGHOST="${PGHOST:-localhost}"' \
    'PGPORT="${PGPORT:-5432}"' \
    'PGDATABASE="${PGDATABASE:-limesurvey}"' \
    'PGUSER="${PGUSER:-limesurvey}"' \
    'PGPASSWORD="${PGPASSWORD:-}"' \
    '' \
    '# Generate config.php' \
    'cat > /var/www/limesurvey/application/config/config.php << CONFEOF' \
    '<?php' \
    'return array(' \
    '    '"'"'components'"'"' => array(' \
    '        '"'"'db'"'"' => array(' \
    '            '"'"'connectionString'"'"' => '"'"'pgsql:host=${PGHOST};port=${PGPORT};dbname=${PGDATABASE};'"'"',' \
    '            '"'"'username'"'"' => '"'"'${PGUSER}'"'"',' \
    '            '"'"'password'"'"' => '"'"'${PGPASSWORD}'"'"',' \
    '            '"'"'charset'"'"' => '"'"'utf8'"'"',' \
    '            '"'"'tablePrefix'"'"' => '"'"'lime_'"'"',' \
    '        ),' \
    '        '"'"'urlManager'"'"' => array(' \
    '            '"'"'urlFormat'"'"' => '"'"'path'"'"',' \
    '            '"'"'showScriptName'"'"' => false,' \
    '        ),' \
    '    ),' \
    '    '"'"'config'"'"' => array(' \
    '        '"'"'debug'"'"' => 0,' \
    '        '"'"'debugsql'"'"' => 0,' \
    '    ),' \
    ');' \
    'CONFEOF' \
    '' \
    '# Link upload directory to persistent storage' \
    'rm -rf /var/www/limesurvey/upload' \
    'ln -sf /var/lib/limesurvey/upload /var/www/limesurvey/upload' \
    '' \
    '# Set permissions' \
    'chown -R www-data:www-data /var/www/limesurvey /var/lib/limesurvey' \
    'chmod -R 755 /var/www/limesurvey/tmp 2>/dev/null || true' \
    'chmod -R 755 /var/lib/limesurvey/upload' \
    '' \
    '# Initialize database if not done (check for settings_global table)' \
    'ADMIN_USER="${ADMIN_USER:-admin}"' \
    'ADMIN_NAME="${ADMIN_NAME:-Administrator}"' \
    'ADMIN_EMAIL="${ADMIN_EMAIL:-admin@example.com}"' \
    'ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin123}"' \
    '' \
    '# Run LimeSurvey CLI installer if database is empty' \
    'cd /var/www/limesurvey' \
    'php application/commands/console.php install "$ADMIN_USER" "$ADMIN_PASSWORD" "$ADMIN_NAME" "$ADMIN_EMAIL" 2>/dev/null || true' \
    '' \
    '# Start Apache in foreground' \
    'exec apache2ctl -D FOREGROUND' \
    > /usr/local/bin/start-limesurvey.sh \
    && chmod +x /usr/local/bin/start-limesurvey.sh

# Environment
ENV APACHE_RUN_USER=www-data
ENV APACHE_RUN_GROUP=www-data
ENV APACHE_LOG_DIR=/var/log/apache2

# Data volume
VOLUME /var/lib/limesurvey/upload

EXPOSE 8080

CMD ["/usr/local/bin/start-limesurvey.sh"]
