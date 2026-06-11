# Shlink URL Shortener (Docker-based)
# Self-hosted URL shortener with analytics
# https://shlink.io/
# Built from pre-built release on debian:bookworm-slim

FROM debian:bookworm-slim

# Install PHP and dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        php8.2-cli \
        php8.2-fpm \
        php8.2-pgsql \
        php8.2-sqlite3 \
        php8.2-curl \
        php8.2-gd \
        php8.2-intl \
        php8.2-mbstring \
        php8.2-xml \
        php8.2-zip \
        php8.2-opcache \
        php8.2-apcu \
        php8.2-gmp \
        curl \
        ca-certificates \
        unzip \
    && rm -rf /var/lib/apt/lists/*

# Shlink version
ARG SHLINK_VERSION=4.3.1

# Download and extract Shlink (use pre-built release)
WORKDIR /var/www/shlink
RUN curl -fsSL "https://github.com/shlinkio/shlink/releases/download/v${SHLINK_VERSION}/shlink${SHLINK_VERSION}_php8.2_dist.zip" -o shlink.zip && \
    unzip -q shlink.zip && \
    rm shlink.zip && \
    mv shlink${SHLINK_VERSION}_php8.2_dist/* . && \
    rmdir shlink${SHLINK_VERSION}_php8.2_dist && \
    mkdir -p data/cache data/log data/locks data/db && \
    chown -R www-data:www-data /var/www/shlink

# Copy startup script
COPY --chmod=755 start.sh /start.sh

# Runtime environment
ENV DEFAULT_DOMAIN=localhost \
    IS_HTTPS_ENABLED=false \
    SKIP_INITIAL_GEOLITE_DOWNLOAD=true

EXPOSE 8080

CMD ["/start.sh"]
