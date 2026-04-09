#!/bin/bash
set -e

# Validate required environment variables (injected by Hop3)
: "${MYSQL_HOST:?ERROR: MYSQL_HOST is required}"
: "${MYSQL_PORT:?ERROR: MYSQL_PORT is required}"
: "${MYSQL_DATABASE:?ERROR: MYSQL_DATABASE is required}"
: "${MYSQL_USER:?ERROR: MYSQL_USER is required}"
: "${MYSQL_PASSWORD:?ERROR: MYSQL_PASSWORD is required}"

# Optional with defaults
APP_URL="${APP_URL:-localhost}"

cd /var/www/html

# Wait for MySQL to be ready
echo "Waiting for MySQL at ${MYSQL_HOST}:${MYSQL_PORT}..."
for i in $(seq 1 30); do
    if php -r "new PDO('mysql:host=${MYSQL_HOST};port=${MYSQL_PORT};dbname=${MYSQL_DATABASE}', '${MYSQL_USER}', '${MYSQL_PASSWORD}');" 2>/dev/null; then
        echo "MySQL is ready."
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "WARNING: MySQL not ready after 30 attempts."
    fi
    sleep 2
done

# Create config.ini.php if not exists
if [ ! -f config/config.ini.php ]; then
    cat > config/config.ini.php << EOF
; <?php exit; ?> DO NOT REMOVE THIS LINE
[database]
host = "${MYSQL_HOST}"
username = "${MYSQL_USER}"
password = "${MYSQL_PASSWORD}"
dbname = "${MYSQL_DATABASE}"
tables_prefix = matomo_

[General]
salt = "$(head -c 32 /dev/urandom | base64 | tr -d /=+ | head -c 32)"
trusted_hosts[] = "${APP_URL}"
installation_in_progress = 1
force_ssl = 0
proxy_client_headers[] = HTTP_X_FORWARDED_FOR
proxy_host_headers[] = HTTP_X_FORWARDED_HOST

[Plugins]
Plugins[] = CorePluginsAdmin
Plugins[] = CoreAdminHome
Plugins[] = CoreHome
Plugins[] = WebsiteMeasurable
Plugins[] = Diagnostics
Plugins[] = CoreVisualizations
Plugins[] = Proxy
Plugins[] = API
Plugins[] = Widgetize
Plugins[] = LanguagesManager
Plugins[] = Actions
Plugins[] = Dashboard
Plugins[] = MultiSites
Plugins[] = Referrers
Plugins[] = UserLanguage
Plugins[] = DevicesDetection
Plugins[] = Goals
Plugins[] = SEO
Plugins[] = Events
Plugins[] = UserCountry
Plugins[] = VisitsSummary
Plugins[] = VisitFrequency
Plugins[] = VisitTime
Plugins[] = VisitorInterest
Plugins[] = RssWidget
Plugins[] = Feedback
Plugins[] = CoreUpdater
Plugins[] = CoreConsole
Plugins[] = ScheduledReports
Plugins[] = UserCountryMap
Plugins[] = Live
Plugins[] = PrivacyManager
Plugins[] = ImageGraph
Plugins[] = Annotations
Plugins[] = MobileMessaging
Plugins[] = Overlay
Plugins[] = SegmentEditor
Plugins[] = Insights
Plugins[] = Morpheus
Plugins[] = Contents
Plugins[] = BulkTracking
Plugins[] = Resolution
Plugins[] = DevicePlugins
Plugins[] = Heartbeat
Plugins[] = Intl
Plugins[] = UsersManager
Plugins[] = SitesManager
Plugins[] = Login
Plugins[] = TwoFactorAuth

PluginsInstalled[] = CorePluginsAdmin
PluginsInstalled[] = CoreAdminHome
PluginsInstalled[] = CoreHome
PluginsInstalled[] = WebsiteMeasurable
PluginsInstalled[] = Diagnostics
PluginsInstalled[] = CoreVisualizations
PluginsInstalled[] = Proxy
PluginsInstalled[] = API
PluginsInstalled[] = Widgetize
PluginsInstalled[] = LanguagesManager
PluginsInstalled[] = Actions
PluginsInstalled[] = Dashboard
PluginsInstalled[] = MultiSites
PluginsInstalled[] = Referrers
PluginsInstalled[] = UserLanguage
PluginsInstalled[] = DevicesDetection
PluginsInstalled[] = Goals
PluginsInstalled[] = SEO
PluginsInstalled[] = Events
PluginsInstalled[] = UserCountry
PluginsInstalled[] = VisitsSummary
PluginsInstalled[] = VisitFrequency
PluginsInstalled[] = VisitTime
PluginsInstalled[] = VisitorInterest
PluginsInstalled[] = RssWidget
PluginsInstalled[] = Feedback
PluginsInstalled[] = CoreUpdater
PluginsInstalled[] = CoreConsole
PluginsInstalled[] = ScheduledReports
PluginsInstalled[] = UserCountryMap
PluginsInstalled[] = Live
PluginsInstalled[] = PrivacyManager
PluginsInstalled[] = ImageGraph
PluginsInstalled[] = Annotations
PluginsInstalled[] = MobileMessaging
PluginsInstalled[] = Overlay
PluginsInstalled[] = SegmentEditor
PluginsInstalled[] = Insights
PluginsInstalled[] = Morpheus
PluginsInstalled[] = Contents
PluginsInstalled[] = BulkTracking
PluginsInstalled[] = Resolution
PluginsInstalled[] = DevicePlugins
PluginsInstalled[] = Heartbeat
PluginsInstalled[] = Intl
PluginsInstalled[] = UsersManager
PluginsInstalled[] = SitesManager
PluginsInstalled[] = Login
PluginsInstalled[] = TwoFactorAuth
EOF
    chown www-data:www-data config/config.ini.php
fi

# Ensure directories are writable
chown -R www-data:www-data tmp config
chmod -R 755 tmp config

# Start Apache
exec apache2ctl -D FOREGROUND
