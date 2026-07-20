# LimeSurvey Dockerfile for Hop3
# Professional online survey tool

FROM debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd

ENV DEBIAN_FRONTEND=noninteractive

# Install Apache, PHP, and dependencies
RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
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

# Copy startup script
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Environment
ENV APACHE_RUN_USER=www-data
ENV APACHE_RUN_GROUP=www-data
ENV APACHE_LOG_DIR=/var/log/apache2

# Data volume
VOLUME /var/lib/limesurvey/upload

EXPOSE 8080

CMD ["/usr/local/bin/start.sh"]
