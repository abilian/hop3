#!/bin/bash
# Piwigo start script for Hop3

set -eu

DATA_DIR="${HOP3_DATA_DIR:-/app/data}"
CODE_DIR="${HOP3_CODE_DIR:-/app/code}"
HOP3_USER="${HOP3_USER:-www-data}"

echo "=> Ensure directories and permissions"
mkdir -p /run/piwigo "${DATA_DIR}/_data" "${DATA_DIR}/galleries" "${DATA_DIR}/upload" "${DATA_DIR}/plugins" "${DATA_DIR}/local/config" "${DATA_DIR}/language" "${DATA_DIR}/themes"

if [[ ! -f "${DATA_DIR}/php.ini" ]]; then
    echo -e "; Add custom PHP configuration in this file\n; Settings here are merged with the package's built-in php.ini\n\n" > "${DATA_DIR}/php.ini"
fi

# setup waits for apache to start and configures piwigo
setup() {
    if [[ ! -f "${DATA_DIR}/_data/dummy.txt" ]]; then
        echo "=> Detected first run"
        cp -r "${CODE_DIR}/_plugins"/* "${DATA_DIR}/plugins/"
        cp -r "${CODE_DIR}/_themes"/* "${DATA_DIR}/themes/"
        cp -r "${CODE_DIR}/_language"/* "${DATA_DIR}/language/"
        cp -r "${CODE_DIR}/_local"/* "${DATA_DIR}/local/"
        cp "${CODE_DIR}/_data_old/dummy.txt" "${DATA_DIR}/_data/"
    fi

    while [[ ! -f "/var/run/apache2/apache2.pid" ]]; do
        echo "=> Waiting for apache2 to start"
        sleep 3
    done

    echo "=> Fixup permissions"
    chown -R ${HOP3_USER}:${HOP3_USER} "${DATA_DIR}" /run/piwigo

    echo "=> Setup piwigo"

    curl -L -X POST --data "?language=en_UK&install=true&dbhost=${MYSQL_HOST:-localhost}&dbuser=${MYSQL_USERNAME:-piwigo}&dbpasswd=${MYSQL_PASSWORD:-}&dbname=${MYSQL_DATABASE:-piwigo}&admin_name=admin&admin_pass1=changeme&admin_pass2=changeme&admin_mail=admin@cloudron.local" "http://localhost:8000/install.php"

    sed -e "s/\$conf\['db_base'\] = .*/\$conf\['db_base'\] = getenv('MYSQL_DATABASE');/" \
        -e "s/\$conf\['db_user'\] = .*/\$conf\['db_user'\] = getenv('MYSQL_USERNAME');/" \
        -e "s/\$conf\['db_password'\] = .*/\$conf\['db_password'\] = getenv('MYSQL_PASSWORD');/" \
        -e "s/\$conf\['db_host'\] = .*/\$conf\['db_host'\] = getenv('MYSQL_HOST');/" \
        -i "${DATA_DIR}/local/config/database.inc.php"

    cat << 'EOT' > "${DATA_DIR}/local/config/config.inc.php"
<?php
if (!empty($_SERVER['HTTP_X_FORWARDED_FOR'])) $_SERVER['HTTP_HOST'] = $_SERVER['HTTP_X_FORWARDED_HOST'];
if ($_SERVER['HTTP_X_FORWARDED_PROTO'] == 'https') $_SERVER['HTTPS']='on';

$conf['send_bcc_mail_webmaster'] = false;
$conf['mail_allow_html'] = true;

$conf['mail_sender_name'] = getenv('MAIL_FROM_DISPLAY_NAME') ?? 'Piwigo';
$conf['mail_sender_email'] = getenv('MAIL_FROM');
$conf['smtp_host'] = getenv('SMTP_HOST') . ':' . getenv('SMTP_PORT');
$conf['smtp_user'] = getenv('SMTP_USERNAME');
$conf['smtp_password'] = getenv('SMTP_PASSWORD');
$conf['smtp_secure'] = null;
?>
EOT

    echo "=> Piwigo initialized"
}

if [[ ! -f "${DATA_DIR}/local/config/config.inc.php" ]]; then
    echo "=> First run"
    ( setup ) &
else
    echo "=> Sync up themes (required from 15 -> 16)"
    rsync -avc "${CODE_DIR}/_themes"/* "${DATA_DIR}/themes/"

    echo "=> Fixup permissions"
    chown -R ${HOP3_USER}:${HOP3_USER} "${DATA_DIR}" /run/piwigo
fi

echo "=> Run apache"
APACHE_CONFDIR="" source /etc/apache2/envvars
rm -f "${APACHE_PID_FILE}"

exec /usr/sbin/apache2 -DFOREGROUND
