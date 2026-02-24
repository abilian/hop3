# Dolibarr Dockerfile for Hop3
# Open source ERP and CRM

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
    php-curl \
    php-intl \
    php-soap \
    php-calendar \
    php-imap \
    php-ldap \
    curl \
    ca-certificates \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Configure Apache
RUN a2enmod rewrite \
    && echo "ServerName localhost" >> /etc/apache2/apache2.conf

# Create directories
RUN mkdir -p /var/www/dolibarr /var/lib/dolibarr/documents \
    && chown -R www-data:www-data /var/www/dolibarr /var/lib/dolibarr

WORKDIR /var/www/dolibarr

# Download Dolibarr
ARG DOLIBARR_VERSION=19.0.3
RUN curl -fsSL "https://github.com/Dolibarr/dolibarr/archive/refs/tags/${DOLIBARR_VERSION}.tar.gz" \
    -o /tmp/dolibarr.tar.gz \
    && tar -xzf /tmp/dolibarr.tar.gz --strip-components=1 -C /var/www/dolibarr \
    && rm /tmp/dolibarr.tar.gz \
    && chown -R www-data:www-data /var/www/dolibarr

# Configure Apache virtual host
RUN printf '%s\n' \
    '<VirtualHost *:8080>' \
    '    DocumentRoot /var/www/dolibarr/htdocs' \
    '    <Directory /var/www/dolibarr/htdocs>' \
    '        AllowOverride All' \
    '        Require all granted' \
    '    </Directory>' \
    '    ErrorLog ${APACHE_LOG_DIR}/error.log' \
    '    CustomLog ${APACHE_LOG_DIR}/access.log combined' \
    '</VirtualHost>' \
    > /etc/apache2/sites-available/dolibarr.conf \
    && a2dissite 000-default \
    && a2ensite dolibarr \
    && sed -i 's/Listen 80/Listen 8080/' /etc/apache2/ports.conf

# Create startup script
RUN printf '%s\n' '#!/bin/bash' \
    'set -e' \
    '' \
    '# Database configuration (Hop3 injects PG* vars)' \
    'PGHOST="${PGHOST:-localhost}"' \
    'PGPORT="${PGPORT:-5432}"' \
    'PGDATABASE="${PGDATABASE:-dolibarr}"' \
    'PGUSER="${PGUSER:-dolibarr}"' \
    'PGPASSWORD="${PGPASSWORD:-}"' \
    '' \
    '# Generate conf.php' \
    'cat > /var/www/dolibarr/htdocs/conf/conf.php << CONFEOF' \
    '<?php' \
    '\$dolibarr_main_url_root = '"'"'${DOLI_URL_ROOT:-http://localhost:8080}'"'"';' \
    '\$dolibarr_main_document_root = '"'"'/var/www/dolibarr/htdocs'"'"';' \
    '\$dolibarr_main_url_root_alt = '"'"'/custom'"'"';' \
    '\$dolibarr_main_document_root_alt = '"'"'/var/www/dolibarr/htdocs/custom'"'"';' \
    '\$dolibarr_main_data_root = '"'"'/var/lib/dolibarr/documents'"'"';' \
    '\$dolibarr_main_db_host = '"'"'${PGHOST}'"'"';' \
    '\$dolibarr_main_db_port = '"'"'${PGPORT}'"'"';' \
    '\$dolibarr_main_db_name = '"'"'${PGDATABASE}'"'"';' \
    '\$dolibarr_main_db_user = '"'"'${PGUSER}'"'"';' \
    '\$dolibarr_main_db_pass = '"'"'${PGPASSWORD}'"'"';' \
    '\$dolibarr_main_db_type = '"'"'pgsql'"'"';' \
    '\$dolibarr_main_db_character_set = '"'"'utf8'"'"';' \
    '\$dolibarr_main_db_collation = '"'"'utf8_general_ci'"'"';' \
    '\$dolibarr_main_authentication = '"'"'dolibarr'"'"';' \
    '\$dolibarr_main_prod = 1;' \
    '\$dolibarr_main_force_https = 0;' \
    '\$dolibarr_main_restrict_os_commands = '"'"'mysqldump, mysql, pg_dump, psql'"'"';' \
    '\$dolibarr_nocsrfcheck = 0;' \
    '\$dolibarr_main_instance_unique_id = '"'"'${DOLI_INSTANCE_ID:-hop3_dolibarr}'"'"';' \
    'CONFEOF' \
    '' \
    '# Set permissions' \
    'chown -R www-data:www-data /var/www/dolibarr /var/lib/dolibarr' \
    'chmod 644 /var/www/dolibarr/htdocs/conf/conf.php' \
    '' \
    '# Start Apache in foreground' \
    'exec apache2ctl -D FOREGROUND' \
    > /usr/local/bin/start-dolibarr.sh \
    && chmod +x /usr/local/bin/start-dolibarr.sh

# Environment
ENV APACHE_RUN_USER=www-data
ENV APACHE_RUN_GROUP=www-data
ENV APACHE_LOG_DIR=/var/log/apache2

# Data volume
VOLUME /var/lib/dolibarr/documents

EXPOSE 8080

CMD ["/usr/local/bin/start-dolibarr.sh"]
