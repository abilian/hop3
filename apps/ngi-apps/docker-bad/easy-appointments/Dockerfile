# Easy!Appointments Dockerfile for Hop3
# Open source appointment scheduling

FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install Apache, PHP, and required extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    apache2 \
    libapache2-mod-php8.2 \
    php8.2 \
    php8.2-mysql \
    php8.2-mbstring \
    php8.2-curl \
    php8.2-xml \
    php8.2-gd \
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

# Create startup script
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
cd /var/www/html\n\
\n\
# Create config.php from environment variables\n\
cat > config.php << EOF\n\
<?php\n\
class Config {\n\
    const BASE_URL = getenv("APP_URL") ?: "http://localhost:8080";\n\
    const LANGUAGE = "english";\n\
    const DEBUG_MODE = false;\n\
\n\
    const DB_HOST = getenv("MYSQL_HOST") ?: "localhost";\n\
    const DB_NAME = getenv("MYSQL_DATABASE") ?: "easyappointments";\n\
    const DB_USERNAME = getenv("MYSQL_USER") ?: "easyappointments";\n\
    const DB_PASSWORD = getenv("MYSQL_PASSWORD") ?: "";\n\
\n\
    const GOOGLE_SYNC_FEATURE = false;\n\
    const GOOGLE_CLIENT_ID = "";\n\
    const GOOGLE_CLIENT_SECRET = "";\n\
}\n\
EOF\n\
\n\
chown www-data:www-data config.php\n\
\n\
# Ensure storage is writable\n\
chown -R www-data:www-data storage\n\
chmod -R 755 storage\n\
\n\
# Start Apache\n\
exec apache2ctl -D FOREGROUND\n\
' > /usr/local/bin/start-easyappointments.sh \
    && chmod +x /usr/local/bin/start-easyappointments.sh

# Configure Apache
RUN echo 'Listen 8080' > /etc/apache2/ports.conf \
    && printf '<VirtualHost *:8080>\n    DocumentRoot /var/www/html\n    <Directory /var/www/html>\n        AllowOverride All\n        Require all granted\n    </Directory>\n</VirtualHost>\n' > /etc/apache2/sites-available/000-default.conf
RUN echo 'ServerName localhost' >> /etc/apache2/apache2.conf

EXPOSE 8080

CMD ["/usr/local/bin/start-easyappointments.sh"]
