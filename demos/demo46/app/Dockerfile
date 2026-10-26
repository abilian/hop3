# Demo 46: Minimal PHP with MySQL
# Test PHP + MySQL connectivity

FROM php:8.3-apache@sha256:0d46cb96775228313d3997c155f78227de13bf9972e0c736e653fb23aded79b2

# Install mysqli extension
RUN docker-php-ext-install mysqli pdo pdo_mysql

# Copy application with proper permissions
COPY --chmod=644 index.php /var/www/html/

EXPOSE 80
