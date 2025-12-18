# Demo 41: Piwigo Photo Gallery
# Self-hosted photo management and gallery
# https://piwigo.org/
# Built from source on debian:bookworm-slim

FROM debian:bookworm-slim

# Install Apache, PHP and extensions required by Piwigo
RUN apt-get update && apt-get install -y --no-install-recommends \
        apache2 \
        libapache2-mod-php \
        php-mysql \
        php-gd \
        php-curl \
        php-xml \
        php-mbstring \
        php-exif \
        php-intl \
        curl \
        ca-certificates \
        unzip \
    && rm -rf /var/lib/apt/lists/* \
    && a2enmod rewrite

# Piwigo version
ARG PIWIGO_VERSION=16.1.0

# Download and extract Piwigo from GitHub
WORKDIR /var/www/html
RUN rm -rf /var/www/html/* \
    && curl -fsSL "https://github.com/Piwigo/Piwigo/archive/refs/tags/${PIWIGO_VERSION}.tar.gz" | \
       tar -xz --strip-components=1 \
    && mkdir -p _data/i galleries upload local/config \
    && chown -R www-data:www-data /var/www/html

# Configure Apache
RUN sed -i 's/AllowOverride None/AllowOverride All/' /etc/apache2/apache2.conf \
    && echo "ServerName localhost" >> /etc/apache2/apache2.conf

# Copy startup script
COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 80

CMD ["/start.sh"]
