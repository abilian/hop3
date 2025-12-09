#!/bin/bash
# Kanboard start script for Hop3

set -eu

DATA_DIR="${HOP3_DATA_DIR:-/app/data}"
CODE_DIR="${HOP3_CODE_DIR:-/app/code}"
PKG_DIR="${HOP3_PKG_DIR:-/app/pkg}"

mkdir -p "${DATA_DIR}/plugins" "${DATA_DIR}/data" /run/kanboard/sessions

echo -e "[client]\npassword=${MYSQL_PASSWORD:-}" > /run/kanboard/mysql-extra
readonly mysql="mysql --defaults-file=/run/kanboard/mysql-extra --user=${MYSQL_USERNAME:-kanboard} --host=${MYSQL_HOST:-localhost} -P ${MYSQL_PORT:-3306} ${MYSQL_DATABASE:-kanboard}"

setup_application_url() {
    set -eu

    if $mysql -e "REPLACE INTO settings (\`option\`, \`value\`) VALUES (\"application_url\", \"${HOP3_APP_ORIGIN:-http://localhost}/\")" 2>/dev/null; then
        echo "==> Application URL updated"
    else
        echo "==> Failed to set application url"
    fi
}

setup_oidc() {
    echo "==> Ensure OIDC settings"

    cp -rf "${CODE_DIR}/plugins.orig/OAuth2" "${DATA_DIR}/plugins"

    OIDC_SETTINGS=$(cat <<EOT
REPLACE INTO settings (\`option\`, \`value\`) VALUES ("oauth2_account_creation", "1");
REPLACE INTO settings (\`option\`, \`value\`) VALUES ("oauth2_authorize_url", "${OIDC_AUTH_ENDPOINT}");
REPLACE INTO settings (\`option\`, \`value\`) VALUES ("oauth2_client_id", "${OIDC_CLIENT_ID}");
REPLACE INTO settings (\`option\`, \`value\`) VALUES ("oauth2_client_secret", "${OIDC_CLIENT_SECRET}");
REPLACE INTO settings (\`option\`, \`value\`) VALUES ("oauth2_email_domains", "");
REPLACE INTO settings (\`option\`, \`value\`) VALUES ("oauth2_key_email", "email");
REPLACE INTO settings (\`option\`, \`value\`) VALUES ("oauth2_key_group_filter", "");
REPLACE INTO settings (\`option\`, \`value\`) VALUES ("oauth2_key_groups", "");
REPLACE INTO settings (\`option\`, \`value\`) VALUES ("oauth2_key_name", "name");
REPLACE INTO settings (\`option\`, \`value\`) VALUES ("oauth2_key_user_id", "sub");
REPLACE INTO settings (\`option\`, \`value\`) VALUES ("oauth2_key_username", "preferred_username");
REPLACE INTO settings (\`option\`, \`value\`) VALUES ("oauth2_scopes", "openid profile email");
REPLACE INTO settings (\`option\`, \`value\`) VALUES ("oauth2_token_url", "${OIDC_TOKEN_ENDPOINT}");
REPLACE INTO settings (\`option\`, \`value\`) VALUES ("oauth2_user_api_url", "${OIDC_PROFILE_ENDPOINT}");
EOT
    )
    echo ${OIDC_SETTINGS} | $mysql 2>/dev/null
}

# Generate config from template
sed -e "s/##MAIL_FROM##/${MAIL_FROM:-noreply@localhost}/" \
    -e "s/##SMTP_HOST##/${SMTP_HOST:-localhost}/" \
    -e "s/##SMTP_PORT##/${SMTP_PORT:-25}/" \
    -e "s/##SMTP_USERNAME##/${SMTP_USERNAME:-}/" \
    -e "s/##SMTP_PASSWORD##/${SMTP_PASSWORD:-}/" \
    -e "s/##MYSQL_USERNAME##/${MYSQL_USERNAME:-kanboard}/" \
    -e "s/##MYSQL_PASSWORD##/${MYSQL_PASSWORD:-}/" \
    -e "s/##MYSQL_HOST##/${MYSQL_HOST:-localhost}/" \
    -e "s/##MYSQL_PORT##/${MYSQL_PORT:-3306}/" \
    -e "s/##MYSQL_DATABASE##/${MYSQL_DATABASE:-kanboard}/" \
    "${PKG_DIR}/templates/config.php.template" > /run/kanboard/config.php


if [[ ! -f "${DATA_DIR}/php.ini" ]]; then
    echo -e "; Add custom PHP configuration in this file\n; Settings here are merged with the package's built-in php.ini\n\n" > "${DATA_DIR}/php.ini"
fi

if [[ ! -f "${DATA_DIR}/customconfig.php" ]]; then
    echo "==> Copying customconfig.php.template"
    cp "${PKG_DIR}/templates/customconfig.php.template" "${DATA_DIR}/customconfig.php"
fi

table_count=$($mysql -NB -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = '${MYSQL_DATABASE:-kanboard}';" 2>/dev/null || echo "0")

if [[ "${table_count}" == "0" ]]; then
    echo "==> Initializing database"
    # this is only the seed file, must always run migration afterwards
    cat "${CODE_DIR}/app/Schema/Sql/mysql.sql" | $mysql 2>/dev/null
fi

echo "==> Migrating database"
php "${CODE_DIR}/cli" db:migrate

setup_application_url

if [[ -n "${OIDC_ISSUER:-}" ]]; then
    setup_oidc
fi

chown -R www-data:www-data "${DATA_DIR}" /run/kanboard

echo "==> Starting apache"
APACHE_CONFDIR="" source /etc/apache2/envvars
rm -f "${APACHE_PID_FILE}"
exec /usr/sbin/apache2 -DFOREGROUND
