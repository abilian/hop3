#!/bin/bash
# Easy!Appointments start script for Hop3

set -eu

DATA_DIR="${HOP3_DATA_DIR:-/app/data}"
CODE_DIR="${HOP3_CODE_DIR:-/app/code}"
PKG_DIR="${HOP3_PKG_DIR:-/app/pkg}"
HOP3_USER="${HOP3_USER:-www-data}"

readonly mysql="mysql -u ${MYSQL_USERNAME:-easyappointments} -p${MYSQL_PASSWORD:-} -h ${MYSQL_HOST:-localhost} --port ${MYSQL_PORT:-3306} --database ${MYSQL_DATABASE:-easyappointments}"

echo "=> Ensure directories"
mkdir -p /run/easyappointments/sessions "${DATA_DIR}" /run/easyappointments/logs

if [[ ! -f "${DATA_DIR}/php.ini" ]]; then
    echo -e "; Add custom PHP configuration in this file\n; Settings here are merged with the package's built-in php.ini\n\n" > "${DATA_DIR}/php.ini"
fi

if [[ ! -f "${DATA_DIR}/config.php" ]]; then
    echo "=> Ensure config.php"
    cp "${PKG_DIR}/config-sample.php" "${DATA_DIR}/config.php"
fi

echo "=> Patch config.php"
sed -e "s,const BASE_URL.*,const BASE_URL = '${HOP3_APP_ORIGIN:-http://localhost}';," -i "${DATA_DIR}/config.php"
sed -e "s,const DB_HOST.*,const DB_HOST = '${MYSQL_HOST:-localhost}';," -i "${DATA_DIR}/config.php"
sed -e "s,const DB_NAME.*,const DB_NAME = '${MYSQL_DATABASE:-easyappointments}';," -i "${DATA_DIR}/config.php"
sed -e "s,const DB_USERNAME.*,const DB_USERNAME = '${MYSQL_USERNAME:-easyappointments}';," -i "${DATA_DIR}/config.php"
sed -e "s,const DB_PASSWORD.*,const DB_PASSWORD = '${MYSQL_PASSWORD:-}';," -i "${DATA_DIR}/config.php"

table_count=$($mysql -NB -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = '${MYSQL_DATABASE:-easyappointments}';" 2>/dev/null)

if [[ "${table_count}" == "0" ]]; then
    echo "=> Initial setup"
    sudo -E -u ${HOP3_USER} php "${CODE_DIR}/index.php" console install
else
    echo "=> Migrate database"
    sudo -E -u ${HOP3_USER} php "${CODE_DIR}/index.php" console migrate
fi

echo "=> Ensure company email and name"
$mysql -e "UPDATE ea_settings SET value='${SMTP_USERNAME:-}' WHERE name='company_email'"
$mysql -e "UPDATE ea_settings SET value='${MAIL_FROM_DISPLAY_NAME:-Easy!Appointments}' WHERE name='company_name'"

echo "=> Ensure permissions"
chown -R ${HOP3_USER}:${HOP3_USER} "${DATA_DIR}" /run/easyappointments

echo "=> Starting apache"
APACHE_CONFDIR="" source /etc/apache2/envvars
rm -f "${APACHE_PID_FILE}"
exec /usr/sbin/apache2 -DFOREGROUND
