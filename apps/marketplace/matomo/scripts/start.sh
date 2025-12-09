#!/bin/bash
# Matomo start script for Hop3

set -eu -o pipefail

DATA_DIR="${HOP3_DATA_DIR:-/app/data}"
CODE_DIR="${HOP3_CODE_DIR:-/app/code}"
PKG_DIR="${HOP3_PKG_DIR:-/app/pkg}"

cd "${CODE_DIR}"

readonly console="php ${CODE_DIR}/console"
readonly crudini_cmd="crudini"

echo "=> Ensure directories"
mkdir -p /run/matomo/tmp "${DATA_DIR}/config" "${DATA_DIR}/plugins" "${DATA_DIR}/misc" /run/matomo/session

# remove legacy js folder
rm -rf "${DATA_DIR}/js"

setup() {
    while [[ ! -f "/var/run/apache2/apache2.pid" ]]; do
        echo "Waiting for apache2 to start"
        sleep 1
    done

    if [[ ! -f "${DATA_DIR}/config/config.ini.php" ]]; then
        echo "=> Detected first run"

        echo "=> Configuring database"
        curl --fail 'http://localhost:8000/index.php?action=databaseSetup&clientProtocol=https' --data "type=InnoDB&host=mysql&username=${MYSQL_USERNAME:-matomo}&password=${MYSQL_PASSWORD:-}&dbname=${MYSQL_DATABASE:-matomo}&tables_prefix=&adapter=PDO%5CMYSQL&submit=Next+%C2%BB"

        echo "=> Creating tables"
        curl --fail -X POST 'http://localhost:8000/index.php?action=tablesCreation&clientProtocol=https&module=Installation'

        echo "=> Creating admin"
        curl --fail 'http://localhost:8000/index.php?action=setupSuperUser&clientProtocol=https&module=Installation' --data 'login=admin&password=changeme&password_bis=changeme&email=admin%40localhost&submit=Next+%C2%BB'

        echo "=> Creating example website"
        curl --fail 'http://localhost:8000/index.php?action=firstWebsiteSetup&clientProtocol=https&module=Installation' --data 'siteName=Example&url=https%3A%2F%2Fwww.example.com&timezone=UTC&ecommerce=0&submit=Next+%C2%BB'

        echo "=> Finishing installation"
        curl --fail 'http://localhost:8000/index.php?action=finished&clientProtocol=https&module=Installation&site_idSite=1&site_name=Example' --data 'do_not_track=1&anonymise_ip=1&submit=Continue+to+Matomo+%C2%BB'

        echo "=> Configuring"
        $crudini_cmd --set "${DATA_DIR}/config/config.ini.php" General force_ssl 1
        $crudini_cmd --set "${DATA_DIR}/config/config.ini.php" General enable_update_communication 0
        $crudini_cmd --set "${DATA_DIR}/config/config.ini.php" General enable_auto_update 0
        $crudini_cmd --set "${DATA_DIR}/config/config.ini.php" General piwik_professional_support_ads_enabled 0
        $crudini_cmd --set "${DATA_DIR}/config/config.ini.php" General 'cors_domains[]' '*'
        $crudini_cmd --set "${DATA_DIR}/config/config.ini.php" General enable_trusted_host_check 0

        $crudini_cmd --set "${DATA_DIR}/config/config.ini.php" General "proxy_client_headers[]" "HTTP_X_FORWARDED_FOR"
        $crudini_cmd --set "${DATA_DIR}/config/config.ini.php" General "proxy_host_headers[]" "HTTP_X_FORWARDED_HOST"

        # use php sessions. default is dbtable
        $crudini_cmd --set "${DATA_DIR}/config/config.ini.php" General "session_save_handler" ""
        $crudini_cmd --set "${DATA_DIR}/config/config.ini.php" General "enable_load_data_infile" 0

        # we run archiving via a cron job. disable browser triggered archiving
        mysql -u${MYSQL_USERNAME:-matomo} -p${MYSQL_PASSWORD:-} -h${MYSQL_HOST:-localhost} -P${MYSQL_PORT:-3306} -D${MYSQL_DATABASE:-matomo} -e 'INSERT INTO `option` (option_name, option_value) VALUES ("enableBrowserTriggerArchiving", 0);'

        echo "=> Run cron job to keep system check happy"
        /app/scripts/cron.sh

        # geolocation provider
        mysql -u${MYSQL_USERNAME:-matomo} -p${MYSQL_PASSWORD:-} -h${MYSQL_HOST:-localhost} -P${MYSQL_PORT:-3306} -D${MYSQL_DATABASE:-matomo} -e 'INSERT INTO `option` (option_name, option_value) VALUES ("usercountry.location_provider", "geoip2php");'

    fi

    echo "=> Updating database settings"
    $crudini_cmd --set "${DATA_DIR}/config/config.ini.php" database host "${MYSQL_HOST:-localhost}"
    $crudini_cmd --set "${DATA_DIR}/config/config.ini.php" database port ${MYSQL_PORT:-3306}
    $crudini_cmd --set "${DATA_DIR}/config/config.ini.php" database username "${MYSQL_USERNAME:-matomo}"
    $crudini_cmd --set "${DATA_DIR}/config/config.ini.php" database password "${MYSQL_PASSWORD:-}"
    $crudini_cmd --set "${DATA_DIR}/config/config.ini.php" database dbname "${MYSQL_DATABASE:-matomo}"

    # some existing installations have a table prefix
    if ! tables_prefix=$($crudini_cmd --get "${DATA_DIR}/config/config.ini.php" database tables_prefix 2>/dev/null | xargs); then
        echo "=> no table prefix"
        tables_prefix=""
    else
        echo "=> table prefix:${tables_prefix}"
    fi

    echo "=> Updating email settings"
    $console config:set --section="mail" --key="defaultHostnameIfEmpty" --value="${HOP3_APP_DOMAIN:-localhost}"
    $console config:set --section="mail" --key="transport" --value="smtp"
    $console config:set --section="mail" --key="host" --value="${SMTP_HOST:-localhost}"
    $console config:set --section="mail" --key="port" --value="${SMTP_PORT:-25}"
    $console config:set --section="mail" --key="type" --value="LOGIN"
    $console config:set --section="mail" --key="username" --value="${SMTP_USERNAME:-}"
    $console config:set --section="mail" --key="password" --value="${SMTP_PASSWORD:-}"
    $console config:set --section="mail" --key="encryption" --value=""

    $console config:set --section="General" --key="noreply_email_address" --value="${MAIL_FROM:-noreply@localhost}"
    $console config:set --section="General" --key="login_password_recovery_email_address" --value="${MAIL_FROM:-noreply@localhost}"
    $console config:set --section="General" --key="login_password_recovery_replyto_email_address" --value="${MAIL_FROM:-noreply@localhost}"

    if [[ -n "${OIDC_ISSUER:-}" ]]; then
        echo "=> Updating OIDC settings"

        [[ -z ${OIDC_PROVIDER_NAME:-} ]] && OIDC_PROVIDER_NAME="SSO"
        provider_name=$(php -r "echo addslashes(preg_replace('/[\xF0-\xF7].../s', '', \"${OIDC_PROVIDER_NAME}\"));")
        echo "DELETE FROM \`${tables_prefix}plugin_setting\` WHERE \`plugin_name\`='LoginOIDC' and \`user_login\`=''; INSERT INTO \`${tables_prefix}plugin_setting\` (\`plugin_name\`, \`setting_name\`,  \`setting_value\`, \`user_login\`) VALUES ('LoginOIDC','disableSuperuser','0', ''), ('LoginOIDC','disablePasswordConfirmation','1', ''), ('LoginOIDC','disableDirectLoginUrl','1', ''), ('LoginOIDC','allowSignup','1', ''), ('LoginOIDC','bypassTwoFa','1', ''), ('LoginOIDC','autoLinking','1', ''), ('LoginOIDC','authenticationName','Login with ${provider_name}', ''), ('LoginOIDC','authorizeUrl','${OIDC_AUTH_ENDPOINT}', ''), ('LoginOIDC','tokenUrl','${OIDC_TOKEN_ENDPOINT}', ''), ('LoginOIDC','userinfoUrl','${OIDC_PROFILE_ENDPOINT}', ''), ('LoginOIDC','endSessionUrl','', ''), ('LoginOIDC','userinfoId','sub', ''), ('LoginOIDC', 'useEmailAsUsername', '0', ''), ('LoginOIDC','clientId','${OIDC_CLIENT_ID}', ''), ('LoginOIDC','clientSecret','${OIDC_CLIENT_SECRET}', ''), ('LoginOIDC','scope','openid email profile', ''), ('LoginOIDC','redirectUriOverride','', ''), ('LoginOIDC','allowedSignupDomains','', '');" | mysql -v -u${MYSQL_USERNAME:-matomo} -p${MYSQL_PASSWORD:-} -h${MYSQL_HOST:-localhost} -P${MYSQL_PORT:-3306} -D${MYSQL_DATABASE:-matomo}

        echo "=> Enable OIDC plugin"
        $console plugin:activate LoginOIDC
    fi

    echo "=> Perform db migration"
    $console core:update --yes

    $crudini_cmd --set "${DATA_DIR}/config/config.ini.php" General noreply_email_name "\"${MAIL_FROM_DISPLAY_NAME:-Matomo}\""

    echo "=> Ensure permissions after setup"
    chown -R www-data:www-data /run/matomo "${DATA_DIR}"
}

# Copy built-in plugins
echo "=> Copy built-in plugins"
for dir in "${PKG_DIR}/plugins.orig"/*/; do
    dirWithoutSlash=${dir%/}
    echo "==> Copying ${dirWithoutSlash} ..."
    if [[ -n "${OIDC_ISSUER:-}" || "${dirWithoutSlash}" != "LoginOIDC" ]]; then
        rsync -ac --delete "${dirWithoutSlash}" "${DATA_DIR}/plugins/"
    fi
done

# updates from old versions require the copy even if not a new install
[[ ! -f "${DATA_DIR}/piwik.js" ]] && cp "${PKG_DIR}/piwik.js.orig" "${DATA_DIR}/piwik.js"
[[ ! -f "${DATA_DIR}/matomo.js" ]] && cp "${PKG_DIR}/matomo.js.orig" "${DATA_DIR}/matomo.js"

if [[ ! -f "${DATA_DIR}/php.ini" ]]; then
    echo -e "; Add custom PHP configuration in this file\n; Settings here are merged with the package's built-in php.ini\n\n" > "${DATA_DIR}/php.ini"
fi

# This stores the custom instance logo
echo "=> Handle custom logo if any"
[[ ! -d "${DATA_DIR}/misc/user" ]] && cp -rf "${PKG_DIR}/user.orig" "${DATA_DIR}/misc/user"

echo "=> Ensure permissions"
chown -R www-data:www-data /run/matomo "${DATA_DIR}"

( setup ) &

echo "==> Starting matomo"
APACHE_CONFDIR="" source /etc/apache2/envvars
rm -f "${APACHE_PID_FILE}"
exec /usr/sbin/apache2 -DFOREGROUND
