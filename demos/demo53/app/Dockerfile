# Demo 53: PHP JSON API
# Feature-rich API similar to demo50-52
# Built on debian:bookworm-slim with PHP

FROM debian:bookworm-slim

# Install PHP and Apache
RUN apt-get update && apt-get install -y --no-install-recommends \
        apache2 \
        libapache2-mod-php \
        php-cli \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && a2enmod rewrite

# Configure Apache
RUN echo "ServerName localhost" >> /etc/apache2/apache2.conf
ENV APACHE_RUN_USER=www-data \
    APACHE_RUN_GROUP=www-data \
    APACHE_LOG_DIR=/var/log/apache2

# Enable AllowOverride for .htaccess
RUN sed -i '/<Directory \/var\/www\/>/,/<\/Directory>/ s/AllowOverride None/AllowOverride All/' /etc/apache2/apache2.conf

# Copy application
COPY --chmod=644 index.php .htaccess /var/www/html/
RUN chown -R www-data:www-data /var/www/html

EXPOSE 80

CMD ["apache2ctl", "-D", "FOREGROUND"]
