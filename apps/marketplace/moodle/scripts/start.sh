#!/bin/bash
# Moodle start script for Hop3

set -eu

DATA_DIR="${HOP3_DATA_DIR:-/app/data}"
CODE_DIR="${HOP3_CODE_DIR:-/app/code}"
PKG_DIR="${HOP3_PKG_DIR:-/app/pkg}"

mkdir -p /run/moodle/sessions "${DATA_DIR}/moodledata"

export PGPASSWORD="${POSTGRES_PASSWORD:-}"
readonly pg="psql -h ${POSTGRES_HOST:-localhost} -p ${POSTGRES_PORT:-5432} -U ${POSTGRES_USERNAME:-moodle} -d ${POSTGRES_DATABASE:-moodle}"

readonly src_dir="${DATA_DIR}/moodle"
readonly backup_src_dir="${DATA_DIR}/moodle-prev-do-not-touch"

# create proper dirs instead of symlinks. moodle gets confused with symlinks
rm -rf "${DATA_DIR}/moodledata"/{temp,cache,localcache}
mkdir -p "${DATA_DIR}/moodledata"/{temp,cache,localcache}

# we moved sessions to redis
rm -rf "${DATA_DIR}/moodledata/sessions" && mkdir -p "${DATA_DIR}/moodledata/sessions"

if [[ ! -f "${DATA_DIR}/php.ini" ]]; then
    echo -e "; Add custom PHP configuration in this file\n; Settings here are merged with the package's built-in php.ini\n\n" > "${DATA_DIR}/php.ini"
fi

if [[ ! -f "${DATA_DIR}/.initialized" ]]; then
    echo "==> Fresh installation, performing Moodle first time setup"

    echo "==> Installing new moodle"
    rsync -az "${CODE_DIR}/new/" "${DATA_DIR}/moodle"

    # Copy config template
    cp "${PKG_DIR}/templates/config.php.template" "${DATA_DIR}/moodle/config.php"

    # not sure why this cannot run as www-data user
    php ${src_dir}/admin/cli/install_database.php --lang=en --adminuser=admin --adminpass=changeme123 --adminemail=admin@localhost \
        --fullname='My Moodle Site' --shortname='MySite' --agree-license

    touch "${DATA_DIR}/.initialized"
    echo "==> Installation done."
else
    echo "==> Existing installation. Will upgrade"
    echo "==> Create temporary migration data"
    rm -rf ${backup_src_dir} && mv ${src_dir} ${backup_src_dir}
    echo "==> Copy moodle into /app/data/moodle"
    rsync -az "${CODE_DIR}/new/" "${DATA_DIR}/moodle"

    # Copy config template
    cp "${PKG_DIR}/templates/config.php.template" "${DATA_DIR}/moodle/config.php"

    # https://docs.moodle.org/dev/Plugin_types
    echo "==> Copying over user plugins from old installation"
    if [[ -f "${PKG_DIR}/plugintypes.php" ]]; then
        for subdir in $(php "${PKG_DIR}/plugintypes.php"); do
            [[ ! -d "${backup_src_dir}/public/${subdir}" ]] && continue

            echo "==> Plugin subdir ${subdir}"
            for x in $(find "${backup_src_dir}/public/${subdir}"/* -maxdepth 0 -type d -printf "%f\n" 2>/dev/null || true); do
                [[ -d "${src_dir}/public/${subdir}/${x}" ]] && continue  # do not overwrite plugin from the new version
                if [[ -d "${CODE_DIR}/old/${subdir}/${x}" ]]; then
                    echo "===> Skipping ${x} since it is missing in newer version, probably removed upstream"
                else
                    echo "===> Copying user plugin ${x}"
                    cp -rf "${backup_src_dir}/public/${subdir}/${x}" ${src_dir}/public/${subdir}
                fi
            done
        done
    fi

    echo "==> Upgrading moodle"
    # https://docs.moodle.org/39/en/Administration_via_command_line#Upgrading
    php ${src_dir}/admin/cli/upgrade.php --non-interactive

     rm -rf "${backup_src_dir}"
fi

# SMTP Setup
if [[ -n "${SMTP_HOST:-}" ]]; then
    php ${src_dir}/admin/cli/cfg.php --name=smtphosts --set="${SMTP_HOST}:${SMTP_PORT:-25}"
    php ${src_dir}/admin/cli/cfg.php --name=smtpuser --set="${SMTP_USERNAME:-}"
    php ${src_dir}/admin/cli/cfg.php --name=smtppass --set="${SMTP_PASSWORD:-}"
    php ${src_dir}/admin/cli/cfg.php --name=noreplyaddress --set="${MAIL_FROM:-noreply@localhost}"
fi

if [[ -n "${OIDC_ISSUER:-}" ]]; then
    # https://docs.moodle.org/500/en/OAuth_2_services
    provider_id=$($pg -AXqtc "SELECT id FROM mdl_oauth2_issuer WHERE name = 'Hop3'" 2>/dev/null || echo "")
    readonly admin_id=$($pg -AXqtc "SELECT id FROM mdl_user WHERE username='admin'" 2>/dev/null || echo "1")
    readonly now=$(date +%s)
    if [[ -z "${provider_id}" ]]; then
        echo "INSERT INTO mdl_oauth2_issuer(name, clientid, clientsecret, baseurl, loginscopes, loginscopesoffline, showonloginpage, enabled, loginpagename, usermodified, image, loginparams, loginparamsoffline, alloweddomains, sortorder, requireconfirmation, timecreated, timemodified) VALUES (:'name', :'client_id', :'client_secret', :'oidc_issuer', :'loginscopes', :'loginscopesoffline', 1, 1, :'loginpagename', :'usermodified', '', '', '', '', 1, 0, :'now', :'now')" | $pg -t \
            -v name="Hop3" \
            -v client_id="${OIDC_CLIENT_ID}" \
            -v client_secret="${OIDC_CLIENT_SECRET}" \
            -v oidc_issuer="${OIDC_ISSUER}" \
            -v loginscopes="openid email profile" \
            -v loginscopesoffline="openid email profile" \
            -v loginpagename="${OIDC_PROVIDER_NAME:-SSO}" \
            -v usermodified="${admin_id}" \
            -v now=${now}

        provider_id=$($pg -AXqtc "SELECT id FROM mdl_oauth2_issuer WHERE name = 'Hop3'" 2>/dev/null || echo "")
    else
        echo  "UPDATE mdl_oauth2_issuer SET clientid=:'client_id', clientsecret=:'client_secret', baseurl=:'oidc_issuer', loginpagename=:'loginpagename' WHERE id=:'provider_id'" | $pg -t \
            -v provider_id="${provider_id}" \
            -v client_id="${OIDC_CLIENT_ID}" \
            -v client_secret="${OIDC_CLIENT_SECRET}" \
            -v oidc_issuer="${OIDC_ISSUER}" \
            -v loginpagename="${OIDC_PROVIDER_NAME:-SSO}"
    fi

    if [[ -n "${provider_id}" ]]; then
        $pg -c "DELETE FROM mdl_oauth2_endpoint WHERE issuerid=${provider_id}" 2>/dev/null || true
        $pg -c "INSERT INTO mdl_oauth2_endpoint (issuerid, name, url, usermodified, timecreated, timemodified) VALUES ($provider_id, 'authorization_endpoint', '${OIDC_AUTH_ENDPOINT}', $admin_id, $now, $now)" 2>/dev/null || true
        $pg -c "INSERT INTO mdl_oauth2_endpoint (issuerid, name, url, usermodified, timecreated, timemodified) VALUES ($provider_id, 'token_endpoint', '${OIDC_TOKEN_ENDPOINT}', $admin_id, $now, $now)" 2>/dev/null || true
        $pg -c "INSERT INTO mdl_oauth2_endpoint (issuerid, name, url, usermodified, timecreated, timemodified) VALUES ($provider_id, 'userinfo_endpoint', '${OIDC_PROFILE_ENDPOINT}', $admin_id, $now, $now)" 2>/dev/null || true

        $pg -c "DELETE FROM mdl_oauth2_user_field_mapping WHERE issuerid=${provider_id}" 2>/dev/null || true
        $pg -c "INSERT INTO mdl_oauth2_user_field_mapping (issuerid, externalfield, internalfield, usermodified, timecreated, timemodified) VALUES (${provider_id}, 'email', 'email', $admin_id, $now, $now)" 2>/dev/null || true
        $pg -c "INSERT INTO mdl_oauth2_user_field_mapping (issuerid, externalfield, internalfield, usermodified, timecreated, timemodified) VALUES (${provider_id}, 'given_name', 'firstname', $admin_id, $now, $now)" 2>/dev/null || true
        $pg -c "INSERT INTO mdl_oauth2_user_field_mapping (issuerid, externalfield, internalfield, usermodified, timecreated, timemodified) VALUES (${provider_id}, 'family_name', 'lastname', $admin_id, $now, $now)" 2>/dev/null || true
    fi

    # this enables the oauth2 plugin
    php ${src_dir}/admin/cli/cfg.php --name=auth --set="oauth2"
fi

echo "==> Fixing permissions"
chown -R www-data:www-data /run/moodle "${DATA_DIR}"
chown root:root "${DATA_DIR}/moodle/config.php" 2>/dev/null || true # /report/security/index.php?detail=core_configrw

APACHE_CONFDIR="" source /etc/apache2/envvars
rm -f "${APACHE_PID_FILE}"
exec /usr/sbin/apache2 -DFOREGROUND
