# Demo 42: LimeSurvey
# Open-source survey tool
# https://www.limesurvey.org/
# Built from source on debian:bookworm-slim

FROM debian:bookworm-slim

# Install Apache, PHP and extensions required by LimeSurvey
RUN apt-get update && apt-get install -y --no-install-recommends \
        apache2 \
        libapache2-mod-php \
        php-mysql \
        php-pgsql \
        php-gd \
        php-imap \
        php-ldap \
        php-mbstring \
        php-xml \
        php-zip \
        php-curl \
        php-intl \
        curl \
        ca-certificates \
        unzip \
    && rm -rf /var/lib/apt/lists/* \
    && a2enmod rewrite

# LimeSurvey version (URL encoded + as %2B)
ARG LIMESURVEY_VERSION=6.16.3%2B251215

# Download and extract LimeSurvey
WORKDIR /var/www/html
RUN rm -rf /var/www/html/* \
    && curl -fsSL "https://download.limesurvey.org/latest-master/limesurvey${LIMESURVEY_VERSION}.zip" -o limesurvey.zip \
    && unzip -q limesurvey.zip \
    && mv limesurvey/* . || (ls -la && exit 1) \
    && rmdir limesurvey || true \
    && rm limesurvey.zip \
    && mkdir -p tmp/runtime upload \
    && chown -R www-data:www-data /var/www/html

# Configure Apache
RUN sed -i 's/AllowOverride None/AllowOverride All/' /etc/apache2/apache2.conf \
    && echo "ServerName localhost" >> /etc/apache2/apache2.conf

# Copy startup script
COPY --chmod=755 start.sh /start.sh

EXPOSE 80

CMD ["/start.sh"]
