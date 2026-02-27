# Matomo Dockerfile for Hop3
# Open source web analytics platform

FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install Apache, PHP, and required extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    apache2 \
    libapache2-mod-php8.2 \
    php8.2 \
    php8.2-mysql \
    php8.2-pgsql \
    php8.2-gd \
    php8.2-mbstring \
    php8.2-xml \
    php8.2-curl \
    php8.2-zip \
    php8.2-bcmath \
    php8.2-intl \
    php8.2-ldap \
    curl \
    ca-certificates \
    unzip \
    default-mysql-client \
    && rm -rf /var/lib/apt/lists/* \
    && a2enmod rewrite

WORKDIR /var/www/html

# Download Matomo
ARG MATOMO_VERSION=5.2.1
RUN rm -rf /var/www/html/* \
    && curl -sL "https://builds.matomo.org/matomo-${MATOMO_VERSION}.tar.gz" | tar xz --strip-components=1 \
    && mkdir -p tmp/assets tmp/cache tmp/logs tmp/tcpdf tmp/templates_c \
    && chown -R www-data:www-data /var/www/html

# Create startup script
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
cd /var/www/html\n\
\n\
# Create config.ini.php if not exists\n\
if [ ! -f config/config.ini.php ]; then\n\
    cat > config/config.ini.php << EOF\n\
; <?php exit; ?> DO NOT REMOVE THIS LINE\n\
[database]\n\
host = "${MYSQL_HOST:-localhost}"\n\
username = "${MYSQL_USER:-matomo}"\n\
password = "${MYSQL_PASSWORD}"\n\
dbname = "${MYSQL_DATABASE:-matomo}"\n\
tables_prefix = matomo_\n\
\n\
[General]\n\
salt = "$(head -c 32 /dev/urandom | base64 | tr -d /=+ | head -c 32)"\n\
trusted_hosts[] = "${APP_URL:-localhost}"\n\
force_ssl = 0\n\
proxy_client_headers[] = HTTP_X_FORWARDED_FOR\n\
proxy_host_headers[] = HTTP_X_FORWARDED_HOST\n\
\n\
[Plugins]\n\
Plugins[] = CorePluginsAdmin\n\
Plugins[] = CoreAdminHome\n\
Plugins[] = CoreHome\n\
Plugins[] = WebsiteMeasurable\n\
Plugins[] = Diagnostics\n\
Plugins[] = CoreVisualizations\n\
Plugins[] = Proxy\n\
Plugins[] = API\n\
Plugins[] = Widgetize\n\
Plugins[] = LanguagesManager\n\
Plugins[] = Actions\n\
Plugins[] = Dashboard\n\
Plugins[] = MultiSites\n\
Plugins[] = Referrers\n\
Plugins[] = UserLanguage\n\
Plugins[] = DevicesDetection\n\
Plugins[] = Goals\n\
Plugins[] = SEO\n\
Plugins[] = Events\n\
Plugins[] = UserCountry\n\
Plugins[] = VisitsSummary\n\
Plugins[] = VisitFrequency\n\
Plugins[] = VisitTime\n\
Plugins[] = VisitorInterest\n\
Plugins[] = RssWidget\n\
Plugins[] = Feedback\n\
Plugins[] = CoreUpdater\n\
Plugins[] = CoreConsole\n\
Plugins[] = ScheduledReports\n\
Plugins[] = UserCountryMap\n\
Plugins[] = Live\n\
Plugins[] = PrivacyManager\n\
Plugins[] = ImageGraph\n\
Plugins[] = Annotations\n\
Plugins[] = MobileMessaging\n\
Plugins[] = Overlay\n\
Plugins[] = SegmentEditor\n\
Plugins[] = Insights\n\
Plugins[] = Morpheus\n\
Plugins[] = Contents\n\
Plugins[] = BulkTracking\n\
Plugins[] = Resolution\n\
Plugins[] = DevicePlugins\n\
Plugins[] = Heartbeat\n\
Plugins[] = Intl\n\
Plugins[] = UsersManager\n\
Plugins[] = SitesManager\n\
Plugins[] = Login\n\
Plugins[] = TwoFactorAuth\n\
\n\
PluginsInstalled[] = CorePluginsAdmin\n\
PluginsInstalled[] = CoreAdminHome\n\
PluginsInstalled[] = CoreHome\n\
PluginsInstalled[] = WebsiteMeasurable\n\
PluginsInstalled[] = Diagnostics\n\
PluginsInstalled[] = CoreVisualizations\n\
PluginsInstalled[] = Proxy\n\
PluginsInstalled[] = API\n\
PluginsInstalled[] = Widgetize\n\
PluginsInstalled[] = LanguagesManager\n\
PluginsInstalled[] = Actions\n\
PluginsInstalled[] = Dashboard\n\
PluginsInstalled[] = MultiSites\n\
PluginsInstalled[] = Referrers\n\
PluginsInstalled[] = UserLanguage\n\
PluginsInstalled[] = DevicesDetection\n\
PluginsInstalled[] = Goals\n\
PluginsInstalled[] = SEO\n\
PluginsInstalled[] = Events\n\
PluginsInstalled[] = UserCountry\n\
PluginsInstalled[] = VisitsSummary\n\
PluginsInstalled[] = VisitFrequency\n\
PluginsInstalled[] = VisitTime\n\
PluginsInstalled[] = VisitorInterest\n\
PluginsInstalled[] = RssWidget\n\
PluginsInstalled[] = Feedback\n\
PluginsInstalled[] = CoreUpdater\n\
PluginsInstalled[] = CoreConsole\n\
PluginsInstalled[] = ScheduledReports\n\
PluginsInstalled[] = UserCountryMap\n\
PluginsInstalled[] = Live\n\
PluginsInstalled[] = PrivacyManager\n\
PluginsInstalled[] = ImageGraph\n\
PluginsInstalled[] = Annotations\n\
PluginsInstalled[] = MobileMessaging\n\
PluginsInstalled[] = Overlay\n\
PluginsInstalled[] = SegmentEditor\n\
PluginsInstalled[] = Insights\n\
PluginsInstalled[] = Morpheus\n\
PluginsInstalled[] = Contents\n\
PluginsInstalled[] = BulkTracking\n\
PluginsInstalled[] = Resolution\n\
PluginsInstalled[] = DevicePlugins\n\
PluginsInstalled[] = Heartbeat\n\
PluginsInstalled[] = Intl\n\
PluginsInstalled[] = UsersManager\n\
PluginsInstalled[] = SitesManager\n\
PluginsInstalled[] = Login\n\
PluginsInstalled[] = TwoFactorAuth\n\
EOF\n\
    chown www-data:www-data config/config.ini.php\n\
fi\n\
\n\
# Ensure directories are writable\n\
chown -R www-data:www-data tmp config\n\
chmod -R 755 tmp config\n\
\n\
# Start Apache\n\
exec apache2ctl -D FOREGROUND\n\
' > /usr/local/bin/start-matomo.sh \
    && chmod +x /usr/local/bin/start-matomo.sh

# Configure Apache
RUN echo 'Listen 8080' > /etc/apache2/ports.conf \
    && printf '<VirtualHost *:8080>\n    DocumentRoot /var/www/html\n    <Directory /var/www/html>\n        AllowOverride All\n        Require all granted\n    </Directory>\n</VirtualHost>\n' > /etc/apache2/sites-available/000-default.conf
RUN echo 'ServerName localhost' >> /etc/apache2/apache2.conf

EXPOSE 8080

CMD ["/usr/local/bin/start-matomo.sh"]
