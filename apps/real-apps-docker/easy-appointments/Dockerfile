# Easy!Appointments Dockerfile for Hop3
# Open source appointment scheduling

FROM debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd

ENV DEBIAN_FRONTEND=noninteractive

# Install Apache, PHP, and required extensions
RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    apache2 \
    libapache2-mod-php \
    php \
    php-mysql \
    php-mbstring \
    php-curl \
    php-xml \
    php-gd \
    curl \
    ca-certificates \
    unzip \
    && rm -rf /var/lib/apt/lists/* \
    && a2enmod rewrite

WORKDIR /var/www/html

# Download Easy!Appointments
ARG EA_VERSION=1.5.0
RUN rm -rf /var/www/html/* \
    && curl -sL "https://github.com/alextselegidis/easyappointments/releases/download/${EA_VERSION}/easyappointments-${EA_VERSION}.zip" -o ea.zip \
    && unzip ea.zip \
    && rm ea.zip \
    && chown -R www-data:www-data /var/www/html

# Copy startup script
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Configure Apache
RUN echo 'Listen 8080' > /etc/apache2/ports.conf \
    && printf '<VirtualHost *:8080>\n    DocumentRoot /var/www/html\n    <Directory /var/www/html>\n        AllowOverride All\n        Require all granted\n    </Directory>\n</VirtualHost>\n' > /etc/apache2/sites-available/000-default.conf
RUN echo 'ServerName localhost' >> /etc/apache2/apache2.conf

EXPOSE 8080

CMD ["/usr/local/bin/start.sh"]
