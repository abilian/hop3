#!/bin/bash
# LimeSurvey start script for Hop3

set -eu

DATA_DIR="${HOP3_DATA_DIR:-/app/data}"
CODE_DIR="${HOP3_CODE_DIR:-/app/code}"
PKG_DIR="${HOP3_PKG_DIR:-/app/pkg}"
HOP3_USER="${HOP3_USER:-www-data}"

export MYSQL_PWD=${MYSQL_PASSWORD:-}
mysql="mysql --user=${MYSQL_USERNAME:-limesurvey} --host=${MYSQL_HOST:-localhost} ${MYSQL_DATABASE:-limesurvey}"

# Do not use tmp directly due to tmpreaper removing built assets
mkdir -p /run/limesurvey/sessions /run/limesurvey/tmp/runtime /run/limesurvey/tmp/assets /run/limesurvey/tmp/upload

cp "${PKG_DIR}/config.php" /run/limesurvey/config.php

echo "==> Ensure folders"
mkdir -p "${DATA_DIR}/upload" "${CODE_DIR}/upload/surveys" "${CODE_DIR}/upload/admintheme" "${CODE_DIR}/upload/themes/survey/generalfiles"

if [[ ! -f "${DATA_DIR}/php.ini" ]]; then
    echo -e "; Add custom PHP configuration in this file\n; Settings here are merged with the package's built-in php.ini\n\n" > "${DATA_DIR}/php.ini"
fi

echo "==> Changing ownership"
chown -R ${HOP3_USER}:${HOP3_USER} /run/limesurvey "${DATA_DIR}"

if [[ ! -f "${DATA_DIR}/security.php" ]]; then
    echo "==> Run installation script"
    sudo -E -u ${HOP3_USER} php "${CODE_DIR}/application/commands/console.php" install admin changeme Administrator admin@server.local verbose
    $mysql -e "REPLACE INTO lime_settings_global (stg_name, stg_value) VALUES ('siteadminname', 'Administrator')"
    $mysql -e "UPDATE lime_surveys_groupsettings SET adminemail='${MAIL_FROM:-noreply@localhost}' WHERE owner_id=1"
fi

# db settings take precedence over config.php
$mysql -e "REPLACE INTO lime_settings_global (stg_name, stg_value) VALUES ('force_ssl', 'on')"

echo "==> Configure email"
if [[ -n "${MAIL_FROM:-}" ]]; then
    $mysql -e "REPLACE INTO lime_settings_global (stg_name, stg_value) VALUES ('siteadminemail', '${MAIL_FROM}')"
    display_name=$(echo -n "${MAIL_FROM_DISPLAY_NAME:-LimeSurvey}" | base64)
    $mysql -e "REPLACE INTO lime_settings_global (stg_name, stg_value) VALUES ('siteadminname', FROM_BASE64('${display_name}'))"
    $mysql -e "REPLACE INTO lime_settings_global (stg_name, stg_value) VALUES ('siteadminbounce', '${MAIL_FROM}')"
    $mysql -e "REPLACE INTO lime_settings_global (stg_name, stg_value) VALUES ('emailmethod', 'smtp')"
    $mysql -e "REPLACE INTO lime_settings_global (stg_name, stg_value) VALUES ('emailsmtpssl', '')"
    $mysql -e "REPLACE INTO lime_settings_global (stg_name, stg_value) VALUES ('emailsmtphost', '${SMTP_HOST:-localhost}:${SMTP_PORT:-25}')"
    $mysql -e "REPLACE INTO lime_settings_global (stg_name, stg_value) VALUES ('emailsmtpuser', '${SMTP_USERNAME:-}')"

    encrypted_password=$(sudo -E -u ${HOP3_USER} php "${CODE_DIR}/application/commands/console.php" encrypt "${SMTP_PASSWORD:-}")
    $mysql -e "REPLACE INTO lime_settings_global (stg_name, stg_value) VALUES ('emailsmtppassword', '${encrypted_password}')"
else
    echo "==> app's mail delivery settings disabled not configuring email settings"
fi

if [[ -n "${LDAP_SERVER:-}" ]]; then
    echo "==> Configure LDAP plugin"
    ldap_plugin_id=$($mysql -Bs -e "SELECT id FROM lime_plugins WHERE name='AuthLDAP'")
    $mysql -e "UPDATE lime_plugins SET active=1 WHERE id=${ldap_plugin_id}"

    declare -A ldap_keys
    declare -A ldap_values
    ldap_keys[0]="server";                     ldap_values[${ldap_keys[0]}]="'\"${LDAP_SERVER}\"'"
    ldap_keys[1]="ldapport";                   ldap_values[${ldap_keys[1]}]="'\"${LDAP_PORT:-389}\"'"
    ldap_keys[2]="ldapversion";                ldap_values[${ldap_keys[2]}]="'\"2\"'"
    ldap_keys[3]="ldapoptreferrals";           ldap_values[${ldap_keys[3]}]="'\"0\"'"
    ldap_keys[4]="ldaptls";                    ldap_values[${ldap_keys[4]}]="'null'"
    ldap_keys[5]="ldapmode";                   ldap_values[${ldap_keys[5]}]="'\"searchandbind\"'"
    ldap_keys[6]="userprefix";                 ldap_values[${ldap_keys[6]}]="'null'"
    ldap_keys[7]="domainsuffix";               ldap_values[${ldap_keys[7]}]="'null'"
    ldap_keys[8]="searchuserattribute";        ldap_values[${ldap_keys[8]}]="'\"username\"'"
    ldap_keys[9]="usersearchbase";             ldap_values[${ldap_keys[9]}]="'\"${LDAP_USERS_BASE_DN:-}\"'"
    ldap_keys[10]="extrauserfilter";           ldap_values[${ldap_keys[10]}]="'\"\"'"
    ldap_keys[11]="binddn";                    ldap_values[${ldap_keys[11]}]="'\"${LDAP_BIND_DN:-}\"'"
    ldap_keys[12]="bindpwd";                   ldap_values[${ldap_keys[12]}]="'\"${LDAP_BIND_PASSWORD:-}\"'"
    ldap_keys[13]="mailattribute";             ldap_values[${ldap_keys[13]}]="'\"mail\"'"
    ldap_keys[14]="fullnameattribute";         ldap_values[${ldap_keys[14]}]="'\"displayname\"'"
    ldap_keys[15]="is_default";                ldap_values[${ldap_keys[15]}]="'\"1\"'"
    ldap_keys[16]="autocreate";                ldap_values[${ldap_keys[16]}]="'\"1\"'"
    ldap_keys[17]="automaticsurveycreation";   ldap_values[${ldap_keys[17]}]="'\"1\"'"
    ldap_keys[18]="groupsearchbase";           ldap_values[${ldap_keys[18]}]="'\"\"'"
    ldap_keys[19]="groupsearchfilter";         ldap_values[${ldap_keys[19]}]="'\"\"'"
    ldap_keys[20]="allowInitialUser";          ldap_values[${ldap_keys[20]}]="'\"1\"'"

    for key in ${ldap_keys[@]}; do
        if [[ -z $($mysql -e "SELECT * FROM lime_plugin_settings WHERE plugin_id=${ldap_plugin_id} AND lime_plugin_settings.key='${key}';") ]]; then
            echo "  ==> Insert new ldap config ${key} = ${ldap_values[$key]}"
            $mysql -e "INSERT INTO lime_plugin_settings (plugin_id, lime_plugin_settings.key, value) VALUES (${ldap_plugin_id}, '${key}', ${ldap_values[$key]});"
        else
            echo "  ==> Update ldap config ${key} = ${ldap_values[$key]}"
            $mysql -e "UPDATE lime_plugin_settings SET value=${ldap_values[$key]} WHERE plugin_id=${ldap_plugin_id} AND lime_plugin_settings.key='${key}';"
        fi
    done
fi

echo "==> Run database schema update"
sudo -E -u ${HOP3_USER} php "${CODE_DIR}/application/commands/console.php" updatedb

echo "==> Start LimeSurvey"
APACHE_CONFDIR="" source /etc/apache2/envvars
rm -f "${APACHE_PID_FILE}"
exec /usr/sbin/apache2 -DFOREGROUND
