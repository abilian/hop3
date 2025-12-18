# Demo 37: WordPress
# The world's most popular CMS
# https://wordpress.org/
# Built from source on debian:bookworm-slim

FROM debian:bookworm-slim

# Install Apache, PHP and extensions required by WordPress
RUN apt-get update && apt-get install -y --no-install-recommends \
        apache2 \
        libapache2-mod-php \
        php-mysql \
        php-gd \
        php-curl \
        php-xml \
        php-mbstring \
        php-zip \
        php-intl \
        php-imagick \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && a2enmod rewrite

# WordPress version
ARG WORDPRESS_VERSION=6.7.1

# Download and extract WordPress
WORKDIR /var/www/html
RUN rm -rf /var/www/html/* \
    && curl -fsSL "https://wordpress.org/wordpress-${WORDPRESS_VERSION}.tar.gz" | \
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
