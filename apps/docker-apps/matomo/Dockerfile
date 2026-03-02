# Matomo Dockerfile for Hop3
# Open source web analytics platform

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
    php-intl \
    php-ldap \
    curl \
    ca-certificates \
    unzip \
    default-mysql-client \
    && rm -rf /var/lib/apt/lists/* \
    && a2enmod rewrite

WORKDIR /var/www/html

# Download Matomo
ARG MATOMO_VERSION=5.2.1
RUN rm -rf /var/www/html/* \
    && curl -sL "https://builds.matomo.org/matomo-${MATOMO_VERSION}.tar.gz" | tar xz --strip-components=1 \
    && mkdir -p tmp/assets tmp/cache tmp/logs tmp/tcpdf tmp/templates_c \
    && chown -R www-data:www-data /var/www/html

# Copy startup script
COPY start-matomo.sh /usr/local/bin/start-matomo.sh
RUN chmod +x /usr/local/bin/start-matomo.sh

# Configure Apache
RUN echo 'Listen 8080' > /etc/apache2/ports.conf \
    && printf '<VirtualHost *:8080>\n    DocumentRoot /var/www/html\n    <Directory /var/www/html>\n        AllowOverride All\n        Require all granted\n    </Directory>\n</VirtualHost>\n' > /etc/apache2/sites-available/000-default.conf
RUN echo 'ServerName localhost' >> /etc/apache2/apache2.conf

EXPOSE 8080

CMD ["/usr/local/bin/start-matomo.sh"]
