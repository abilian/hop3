#!/bin/bash
# Nextcloud start script for Hop3

set -eu

DATA_DIR="${HOP3_DATA_DIR:-/app/data}"
CODE_DIR="${HOP3_CODE_DIR:-/app/code}"
PKG_DIR="${HOP3_PKG_DIR:-/app/pkg}"

readonly occ="php ${CODE_DIR}/occ"

export mail_from_sub=$(echo ${MAIL_FROM:-noreply@localhost} | cut -d \@ -f 1)
export mail_domain_sub=$(echo ${MAIL_FROM:-noreply@localhost} | cut -d \@ -f 2)

mkdir -p /run/nextcloud/sessions

if [[ -z "$(ls -A ${DATA_DIR})" ]]; then
    echo "==> Detected first run"
    mkdir -p "${DATA_DIR}/config"
    cp -rf "${PKG_DIR}/apps_template" "${DATA_DIR}/apps"

    # note: the install command patches this htaccess (this is for the code). it also generates /app/data/.htaccess for data-dir
    cp "${PKG_DIR}/htaccess.template" "${DATA_DIR}/htaccess"

    echo "==> Install nextcloud"
    # https://docs.nextcloud.com/server/14/admin_manual/configuration_server/occ_command.html#command-line-installation-label
    php "${CODE_DIR}/occ" maintenance:install --database "pgsql" --database-name "${POSTGRES_DATABASE:-nextcloud}"  --database-user "${POSTGRES_USERNAME:-nextcloud}" --database-pass "${POSTGRES_PASSWORD:-}" --database-host "${POSTGRES_HOST:-localhost}" --database-port ${POSTGRES_PORT:-5432} --admin-user "admin" --admin-pass "changeme" --data-dir "${DATA_DIR}/data" -n
else
    NEW_APPS="${PKG_DIR}/apps_template"
    OLD_APPS="${DATA_DIR}/apps"

    echo "==> Updating apps"

    echo "==> Old apps:"
    ls "${NEW_APPS}/" 2>/dev/null || true
    ls "${OLD_APPS}/" 2>/dev/null || true

    for app in $(find "${NEW_APPS}"/* -maxdepth 0 -type d -printf "%f\n" 2>/dev/null || true); do
        echo "==> Update app: ${app}"
        rm -rf "${OLD_APPS}/${app}"
        cp -rf "${NEW_APPS}/${app}" "${OLD_APPS}"
    done

    echo "==> New apps:"
    ls "${NEW_APPS}/" 2>/dev/null || true
    ls "${OLD_APPS}/" 2>/dev/null || true

    # note: there is also an auto-generated /app/data/.htaccess created by the install script for the data directory
    # this one is for the code directory
    echo "==> Copying htaccess"
    cp "${PKG_DIR}/htaccess.template" "${DATA_DIR}/htaccess"
fi

# ensure symlink for scss files
rm -f "${DATA_DIR}/core" && ln -s "${CODE_DIR}/core" "${DATA_DIR}/core"

chown -R www-data:www-data "${DATA_DIR}/config" "${DATA_DIR}/apps" "${DATA_DIR}/htaccess"
chown www-data:www-data "${DATA_DIR}"
[[ -d "${DATA_DIR}/data" ]] && chown www-data:www-data "${DATA_DIR}/data"

echo "==> update config"
cat > "${DATA_DIR}/config/hop3.config.php" <<EOF
<?php
\$CONFIG = array (
    'trusted_domains' => array ( 0 => '${HOP3_APP_DOMAIN:-localhost}' ),
    'trusted_proxies' => array ( 0 => '${HOP3_PROXY_IP:-}' ),
    'forcessl' => true,
    'mail_smtpmode' => 'smtp',
    'mail_smtpauth' => 1,
    'mail_sendmailmode' => 'smtp',
    'mail_smtpauthtype' => 'LOGIN',
    'mail_smtphost' => '${SMTP_HOST:-localhost}',
    'mail_smtpport' => '${SMTP_PORT:-25}',
    'mail_smtpname' => '${SMTP_USERNAME:-}',
    'mail_smtppassword' => '${SMTP_PASSWORD:-}',
    'mail_from_address' => '${mail_from_sub}',
    'mail_smtpsecure' => '',
    'mail_domain' => '${mail_domain_sub}',
    'maintenance_window_start' => 1,
    'overwrite.cli.url' => '${HOP3_APP_ORIGIN:-http://localhost}/',
    'overwritehost' => '${HOP3_APP_DOMAIN:-localhost}',
    'overwriteprotocol' => 'https',
    'log_type' => 'file',
    'logfile' => '/run/nextcloud/nextcloud.log',
    'loglevel' => 3,
    'dbtype' => 'pgsql',
    'dbname' => '${POSTGRES_DATABASE:-nextcloud}',
    'dbuser' => '${POSTGRES_USERNAME:-nextcloud}',
    'dbpassword' => '${POSTGRES_PASSWORD:-}',
    'dbhost' => '${POSTGRES_HOST:-localhost}',
    'dbtableprefix' => 'oc_',
    'updatechecker' => false,
    'redis' => array(
        'host' => '${REDIS_HOST:-localhost}',
        'port' => ${REDIS_PORT:-6379},
        'password' => '${REDIS_PASSWORD:-}'
    ),
    'memcache.local' => '\OC\Memcache\Redis',
    'memcache.locking' => '\OC\Memcache\Redis',
    'integrity.check.disabled' => true,
    'localstorage.allowsymlinks' => true,
    'htaccess.RewriteBase' => '/',
    'simpleSignUpLink.shown' => false,
    'dns_pinning' => false
);
EOF

if [[ ! -f "${DATA_DIR}/php.ini" ]]; then
    echo -e "; Add custom PHP configuration in this file\n; Settings here are merged with the package's built-in php.ini\n\n" > "${DATA_DIR}/php.ini"
fi

mkdir -p "${DATA_DIR}/apache"
[[ ! -f "${DATA_DIR}/apache/mpm_prefork.conf" ]] && cp "${PKG_DIR}/mpm_prefork.conf" "${DATA_DIR}/apache/mpm_prefork.conf"

echo "==> turning off maintenance mode"
$occ maintenance:mode --off || true
echo "==> running upgrade"
$occ upgrade || true
$occ db:convert-filecache-bigint --no-interaction || true
$occ maintenance:update:htaccess || true
$occ maintenance:repair --include-expensive || true

# patch htaccess to contain full url
sed -e 's,caldav /,caldav https:\/\/%{HTTP_HOST}/,' \
    -e 's,carddav /,carddav https:\/\/%{HTTP_HOST}/,' -i "${DATA_DIR}/htaccess"

# add indices of the share table
$occ db:add-missing-indices || true
$occ db:add-missing-columns || true
$occ db:add-missing-primary-keys || true

# Fix permissions
echo "==> Changing ownership"
chown -R www-data:www-data /run/nextcloud

# OIDC
if [[ -n "${OIDC_ISSUER:-}" ]]; then
    echo "==> Ensure OIDC settings"

    $occ app:install user_oidc || true

    $occ user_oidc:provider "Hop3" --clientid="${OIDC_CLIENT_ID}" --clientsecret="${OIDC_CLIENT_SECRET}" \
        --discoveryuri="${OIDC_DISCOVERY_URL:-${OIDC_ISSUER}/.well-known/openid-configuration}" --scope="openid email profile groups" --mapping-groups="groups" \
        --unique-uid=0 --mapping-uid=sub
fi

# turn configuration
if [[ -n "${TURN_SERVER:-}" ]]; then
    echo "==> Installing and enabling spreed, if needed"
    $occ app:install spreed || true
    $occ app:enable spreed || true

    $occ config:app:set spreed stun_servers --value "[\"${STUN_SERVER}:${STUN_PORT}\"]"
    $occ config:app:set spreed turn_servers --value "[{\"server\":\"${TURN_SERVER}:${TURN_PORT}\",\"secret\":\"${TURN_SECRET}\",\"protocols\":\"udp,tcp\"}]"
fi

# without this, nc will show "Internal server error" on start up
echo "==> Run cron job on startup"
php -f "${CODE_DIR}/cron.php" || true

echo "==> Start NextCloud"
exec /usr/bin/supervisord --configuration /etc/supervisor/supervisord.conf --nodaemon -i NextCloud
