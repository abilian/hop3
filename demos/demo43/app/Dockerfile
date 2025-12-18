# Demo 43: EasyAppointments
# Open-source appointment scheduling
# https://easyappointments.org/
# Built from source on debian:bookworm-slim

FROM debian:bookworm-slim

# Install Apache, PHP and extensions required by EasyAppointments
RUN apt-get update && apt-get install -y --no-install-recommends \
        apache2 \
        libapache2-mod-php \
        php-mysql \
        php-gd \
        php-curl \
        php-mbstring \
        php-intl \
        curl \
        ca-certificates \
        unzip \
    && rm -rf /var/lib/apt/lists/* \
    && a2enmod rewrite

# EasyAppointments version
ARG EA_VERSION=1.5.2

# Download and extract EasyAppointments
WORKDIR /var/www/html
RUN rm -rf /var/www/html/* \
    && curl -fsSL "https://github.com/alextselegidis/easyappointments/releases/download/${EA_VERSION}/easyappointments-${EA_VERSION}.zip" -o ea.zip \
    && unzip -q ea.zip \
    && rm ea.zip \
    && chown -R www-data:www-data /var/www/html

# Configure Apache
RUN sed -i 's/AllowOverride None/AllowOverride All/' /etc/apache2/apache2.conf \
    && echo "ServerName localhost" >> /etc/apache2/apache2.conf

# Copy startup script
COPY --chmod=755 start.sh /start.sh

EXPOSE 80

CMD ["/start.sh"]
