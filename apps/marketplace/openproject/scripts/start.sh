#!/bin/bash
# OpenProject start script for Hop3

set -eu

CODE_DIR="${HOP3_CODE_DIR:-/app/code}"
DATA_DIR="${HOP3_DATA_DIR:-/app/data}"
PKG_DIR="${HOP3_PKG_DIR:-/app/pkg}"
HOP3_USER="${HOP3_USER:-www-data}"

cd "${CODE_DIR}"

IS_UPDATE="false"
if [[ -d "${DATA_DIR}/files" ]]; then
    IS_UPDATE="true"
fi

# Cannot use /tmp for tmp since rails gets confused about deleted cache files
mkdir -p /run/openproject/tmp /tmp/log "${DATA_DIR}/repositories" "${DATA_DIR}/files"

export HOME=/run
export TMPDIR=/run/openproject/tmp

# Setup symlinks
ln -sf /run/database.yml "${CODE_DIR}/config/database.yml"
ln -sf /run/secrets.yml "${CODE_DIR}/config/secrets.yml"
ln -sf /run/openproject/tmp "${CODE_DIR}/tmp"
ln -sf /tmp/log "${CODE_DIR}/log"
ln -sf "${DATA_DIR}/schema.rb" "${CODE_DIR}/db/schema.rb"
ln -sf "${DATA_DIR}/repositories" "${CODE_DIR}/repositories"
ln -sf "${DATA_DIR}/files" "${CODE_DIR}/files"
ln -sf /run/openproject/supervisord.log /var/log/supervisor/supervisord.log

echo "=> Setup database configuration"
sed -e "s!##POSTGRESQL_HOST##!${POSTGRES_HOST:-localhost}!" \
    -e "s!##POSTGRESQL_PORT##!${POSTGRES_PORT:-5432}!" \
    -e "s!##POSTGRESQL_USERNAME##!${POSTGRES_USERNAME:-openproject}!" \
    -e "s!##POSTGRESQL_PASSWORD##!${POSTGRES_PASSWORD:-}!" \
    -e "s!##POSTGRESQL_DATABASE##!${POSTGRES_DATABASE:-openproject}!" \
    "${PKG_DIR}/templates/database.yml.template" > /run/database.yml

# Source custom overrides
if [[ ! -f "${DATA_DIR}/env.sh" ]]; then
    echo -e '# Override env variables \n\n#export OPENPROJECT_LOG__LEVEL="info"\n' > "${DATA_DIR}/env.sh"
fi
source "${DATA_DIR}/env.sh"

# Setting mail from display name is not supported
export ADMIN_EMAIL="${MAIL_FROM:-noreply@localhost}"
export OPENPROJECT_EMAIL__DELIVERY__METHOD="smtp"
export OPENPROJECT_SMTP__ADDRESS="${SMTP_HOST:-localhost}"
export OPENPROJECT_SMTP__PORT="${SMTP_PORT:-25}"
export OPENPROJECT_SMTP__DOMAIN="${MAIL_DOMAIN:-localhost}"
export OPENPROJECT_SMTP__AUTHENTICATION="plain"
export OPENPROJECT_SMTP__USER__NAME="${SMTP_USERNAME:-}"
export OPENPROJECT_SMTP__PASSWORD="${SMTP_PASSWORD:-}"
export OPENPROJECT_SMTP__ENABLE__STARTTLS__AUTO="true"
export OPENPROJECT_HOST__NAME="${HOP3_APP_DOMAIN:-localhost}"

# For psql client
export PGPASSWORD="${POSTGRES_PASSWORD:-}"

echo "=> Setting cookie secret"
export SECRET_KEY_BASE=$(./bin/rails secret)

# Create secrets.yml
sed -e "s!##SECRET_KEY_BASE##!${SECRET_KEY_BASE}!" \
    "${PKG_DIR}/templates/secrets.yml.template" > /run/secrets.yml

echo "=> Migrate database"
./bin/rake db:migrate

echo "=> Seed database if needed"
# We have to disable email delivery to avoid db:seed to send welcome emails to non-existing admin email account
export OPENPROJECT_EMAIL_DELIVERY_METHOD=""
./bin/rake db:seed || true
export OPENPROJECT_EMAIL_DELIVERY_METHOD="smtp"

if [[ -n "${LDAP_URL:-}" ]]; then
    echo "=> Update LDAP config"
    PGPASSWORD="${POSTGRES_PASSWORD:-}" psql -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USERNAME:-openproject}" -d "${POSTGRES_DATABASE:-openproject}" -c " \
        INSERT INTO ldap_auth_sources (id, name, host, port, account, account_password, base_dn, attr_login, attr_firstname, attr_lastname, attr_mail, onthefly_register, tls_mode, created_at, updated_at) \
        VALUES (1, 'Hop3', '${LDAP_HOST:-localhost}', ${LDAP_PORT:-389}, '${LDAP_BIND_DN:-}', '${LDAP_BIND_PASSWORD:-}', '${LDAP_USERS_BASE_DN:-}', 'username', 'givenName', 'sn', 'mail', TRUE, 0, NOW(), NOW()) \
        ON CONFLICT (id) DO UPDATE \
        SET name='Hop3', host='${LDAP_HOST:-localhost}', port=${LDAP_PORT:-389}, account='${LDAP_BIND_DN:-}', account_password='${LDAP_BIND_PASSWORD:-}', base_dn='${LDAP_USERS_BASE_DN:-}', attr_login='username', attr_firstname='givenName', attr_lastname='sn', attr_mail='mail', onthefly_register=TRUE, tls_mode=0, updated_at=NOW();"

    # Only disable password reset for LDAP case
    PGPASSWORD="${POSTGRES_PASSWORD:-}" psql -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USERNAME:-openproject}" -d "${POSTGRES_DATABASE:-openproject}" -c "UPDATE settings SET value=0 WHERE name='self_registration';"
    PGPASSWORD="${POSTGRES_PASSWORD:-}" psql -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USERNAME:-openproject}" -d "${POSTGRES_DATABASE:-openproject}" -c "UPDATE settings SET value=0 WHERE name='lost_password';"
fi

echo "=> Update general config"
PGPASSWORD="${POSTGRES_PASSWORD:-}" psql -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USERNAME:-openproject}" -d "${POSTGRES_DATABASE:-openproject}" -c "UPDATE settings SET value='https' WHERE name='protocol';"
PGPASSWORD="${POSTGRES_PASSWORD:-}" psql -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USERNAME:-openproject}" -d "${POSTGRES_DATABASE:-openproject}" -c "UPDATE settings SET value=8 WHERE name='password_min_length';"
PGPASSWORD="${POSTGRES_PASSWORD:-}" psql -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USERNAME:-openproject}" -d "${POSTGRES_DATABASE:-openproject}" -c "UPDATE settings SET value='smtp' WHERE name='email_delivery_method';"
PGPASSWORD="${POSTGRES_PASSWORD:-}" psql -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USERNAME:-openproject}" -d "${POSTGRES_DATABASE:-openproject}" -c "UPDATE settings SET value='${SMTP_HOST:-localhost}' WHERE name='smtp_address';"
PGPASSWORD="${POSTGRES_PASSWORD:-}" psql -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USERNAME:-openproject}" -d "${POSTGRES_DATABASE:-openproject}" -c "UPDATE settings SET value='${SMTP_PORT:-25}' WHERE name='smtp_port';"
PGPASSWORD="${POSTGRES_PASSWORD:-}" psql -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USERNAME:-openproject}" -d "${POSTGRES_DATABASE:-openproject}" -c "UPDATE settings SET value='${MAIL_DOMAIN:-localhost}' WHERE name='smtp_domain';"
PGPASSWORD="${POSTGRES_PASSWORD:-}" psql -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USERNAME:-openproject}" -d "${POSTGRES_DATABASE:-openproject}" -c "UPDATE settings SET value='plain' WHERE name='smtp_authentication';"
PGPASSWORD="${POSTGRES_PASSWORD:-}" psql -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USERNAME:-openproject}" -d "${POSTGRES_DATABASE:-openproject}" -c "UPDATE settings SET value='${SMTP_USERNAME:-}' WHERE name='smtp_user_name';"
PGPASSWORD="${POSTGRES_PASSWORD:-}" psql -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USERNAME:-openproject}" -d "${POSTGRES_DATABASE:-openproject}" -c "UPDATE settings SET value='${SMTP_PASSWORD:-}' WHERE name='smtp_password';"
PGPASSWORD="${POSTGRES_PASSWORD:-}" psql -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USERNAME:-openproject}" -d "${POSTGRES_DATABASE:-openproject}" -c "UPDATE settings SET value=0 WHERE name='smtp_enable_starttls_auto';"
PGPASSWORD="${POSTGRES_PASSWORD:-}" psql -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USERNAME:-openproject}" -d "${POSTGRES_DATABASE:-openproject}" -c "UPDATE settings SET value='${MAIL_FROM:-noreply@localhost}' WHERE name='mail_from';"
PGPASSWORD="${POSTGRES_PASSWORD:-}" psql -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USERNAME:-openproject}" -d "${POSTGRES_DATABASE:-openproject}" -c "UPDATE settings SET value='${HOP3_APP_DOMAIN:-localhost}' WHERE name='host_name';"
PGPASSWORD="${POSTGRES_PASSWORD:-}" psql -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USERNAME:-openproject}" -d "${POSTGRES_DATABASE:-openproject}" -c "UPDATE settings SET value=1 WHERE name='email_login';"

echo "=> Clear previous cache to reflect db changes"
./bin/rake tmp:clear

echo "=> Fixup the directory permissions"
chown -R ${HOP3_USER}:${HOP3_USER} "${DATA_DIR}" /run /tmp

echo "=> Starting supervisor"
exec /usr/bin/supervisord --configuration /etc/supervisor/supervisord.conf --nodaemon -i OpenProject
