# Demo 39: Matomo Analytics
# Open-source web analytics platform (Google Analytics alternative)
# https://matomo.org/
# Built from source on debian:bookworm-slim

FROM debian:bookworm-slim

# Install Apache, PHP and extensions required by Matomo
RUN apt-get update && apt-get install -y --no-install-recommends \
        apache2 \
        libapache2-mod-php \
        php-mysql \
        php-gd \
        php-curl \
        php-xml \
        php-mbstring \
        php-cli \
        php-ldap \
        php-intl \
        curl \
        ca-certificates \
        unzip \
    && rm -rf /var/lib/apt/lists/* \
    && a2enmod rewrite

# Matomo version
ARG MATOMO_VERSION=5.6.2

# Download and extract Matomo
WORKDIR /var/www/html
RUN rm -rf /var/www/html/* \
    && curl -fsSL "https://builds.matomo.org/matomo-${MATOMO_VERSION}.tar.gz" | \
       tar -xz --strip-components=1 \
    && chown -R www-data:www-data /var/www/html

# Configure Apache
RUN sed -i 's/AllowOverride None/AllowOverride All/' /etc/apache2/apache2.conf \
    && echo "ServerName localhost" >> /etc/apache2/apache2.conf

# Copy startup script
COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 80

CMD ["/start.sh"]
