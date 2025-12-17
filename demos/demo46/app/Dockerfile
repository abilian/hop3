# Demo 46: Minimal PHP with MySQL
# Test PHP + MySQL connectivity

FROM php:8.3-apache

# Install mysqli extension
RUN docker-php-ext-install mysqli pdo pdo_mysql

# Copy application with proper permissions
COPY --chmod=644 index.php /var/www/html/

EXPOSE 80
