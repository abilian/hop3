#!/bin/bash
# Redmine start script for Hop3

set -eu -o pipefail

DATA_DIR="${HOP3_DATA_DIR:-/app/data}"
CODE_DIR="${HOP3_CODE_DIR:-/app/code}"
PKG_DIR="${HOP3_PKG_DIR:-/app/pkg}"
HOP3_USER="${HOP3_USER:-www-data}"

echo "=> Ensure directories"
mkdir -p "${DATA_DIR}"/{files,assets,plugin_assets,themes,redmine_extensions,.ssh}
mkdir -p /run/redmine/{log,tmp/pdf,vendor,dotbundle}
rm -f "${CODE_DIR}/tmp/pids/server.pid"

# Create MySQL credentials file
echo -e "[client]\npassword=${MYSQL_PASSWORD:-}" > /run/redmine/mysql-extra
readonly mysql="mysql --defaults-file=/run/redmine/mysql-extra --user=${MYSQL_USERNAME:-redmine} --host=${MYSQL_HOST:-localhost} -P ${MYSQL_PORT:-3306} ${MYSQL_DATABASE:-redmine}"

export HOME=/tmp

# Copy plugins on first run
[[ ! -d "${DATA_DIR}/plugins" ]] && cp -r "${CODE_DIR}/plugins.orig" "${DATA_DIR}/plugins"

# Setup symlinks and files
cp "${CODE_DIR}/Gemfile.lock.save" /run/redmine/Gemfile.lock
touch /run/redmine/schema.rb
touch "${DATA_DIR}/additional_environment.rb"

# Setup symlinks for runtime directories
ln -sf /run/redmine/dotbundle "${CODE_DIR}/.bundle"
ln -sf /run/redmine/vendor "${CODE_DIR}/vendor"
ln -sf /run/redmine/database.yml "${CODE_DIR}/config/database.yml"
ln -sf /run/redmine/configuration.yml "${CODE_DIR}/config/configuration.yml"
ln -sf "${DATA_DIR}/secrets.yml" "${CODE_DIR}/config/secrets.yml"
ln -sf "${DATA_DIR}/files" "${CODE_DIR}/files"
ln -sf "${DATA_DIR}/assets" "${CODE_DIR}/public/assets"
ln -sf "${DATA_DIR}/plugin_assets" "${CODE_DIR}/public/plugin_assets"
ln -sf "${DATA_DIR}/themes" "${CODE_DIR}/themes"
ln -sf "${DATA_DIR}/plugins" "${CODE_DIR}/plugins"
ln -sf /run/redmine/tmp "${CODE_DIR}/tmp"
ln -sf /run/redmine/log "${CODE_DIR}/log"
ln -sf /run/redmine/Gemfile.lock "${CODE_DIR}/Gemfile.lock"
ln -sf /run/redmine/schema.rb "${CODE_DIR}/db/schema.rb"
ln -sf "${DATA_DIR}/.ssh" "/home/${HOP3_USER}/.ssh"
ln -sf "${DATA_DIR}/additional_environment.rb" "${CODE_DIR}/config/additional_environment.rb"

# Copy ImageMagick policy
cp "${PKG_DIR}/conf/policy.xml" /etc/ImageMagick-6/policy.xml 2>/dev/null || true

# Copy production.rb
cp "${PKG_DIR}/conf/production.rb" "${CODE_DIR}/config/environments/production.rb"

echo "=> Generate database config"
cp "${PKG_DIR}/templates/database.yml.template" /run/redmine/database.yml
yq eval -i ".production.database=\"${MYSQL_DATABASE:-redmine}\"" /run/redmine/database.yml
yq eval -i ".production.host=\"${MYSQL_HOST:-localhost}\"" /run/redmine/database.yml
yq eval -i ".production.port=\"${MYSQL_PORT:-3306}\"" /run/redmine/database.yml
yq eval -i ".production.username=\"${MYSQL_USERNAME:-redmine}\"" /run/redmine/database.yml
yq eval -i ".production.password=\"${MYSQL_PASSWORD:-}\"" /run/redmine/database.yml

echo "=> Generate email config"
cp "${PKG_DIR}/templates/configuration.yml.template" /run/redmine/configuration.yml
yq eval -i ".default.email_delivery.smtp_settings.address=\"${SMTP_HOST:-localhost}\"" /run/redmine/configuration.yml
yq eval -i ".default.email_delivery.smtp_settings.port=${SMTP_PORT:-25}" /run/redmine/configuration.yml
yq eval -i ".default.email_delivery.smtp_settings.domain=\"${MAIL_DOMAIN:-localhost}\"" /run/redmine/configuration.yml
yq eval -i ".default.email_delivery.smtp_settings.user_name=\"${SMTP_USERNAME:-}\"" /run/redmine/configuration.yml
yq eval -i ".default.email_delivery.smtp_settings.password=\"${SMTP_PASSWORD:-}\"" /run/redmine/configuration.yml

echo "=> Fixing /tmp permissions"
# https://blog.diacode.com/fixing-temporary-dir-problems-with-ruby-2
chmod o+t /tmp

# The .done flag is not ideal since it doesn't know if user added/removed a gem behind our back
echo "=> Installing plugin gems"
cp -r "${CODE_DIR}/.bundle.orig"/* /run/redmine/dotbundle/
if [[ ! -f /run/redmine/vendor/.done ]]; then
    echo "=> Copying redmine vendor gems on first run"
    cp -r "${CODE_DIR}/vendor.orig"/* /run/redmine/vendor
    echo "=> Installing gems of plugins"
    cd "${CODE_DIR}" && bundle install
fi
touch /run/redmine/vendor/.done

chown -R ${HOP3_USER}:${HOP3_USER} "${DATA_DIR}" /run/redmine

if [[ ! -f "${DATA_DIR}/secrets.yml" ]]; then
    echo "=> First run"

    echo "=> Generate session secret"
    cd "${CODE_DIR}"
    secret=$(bundle exec rails secret 2>/dev/null)
    cat > "${DATA_DIR}/secrets.yml" <<EOF
production:
  secret_key_base: ${secret}
EOF
    export SECRET_KEY_BASE=$(cat "${DATA_DIR}/secrets.yml" | grep 'secret_key_base:' | sed -e "s/.*secret_key_base:\s*//")
    echo "=> Run database migration"
    su -s /bin/bash ${HOP3_USER} -c "cd ${CODE_DIR} && bundle exec rake db:migrate"

    echo "=> Setup default data"
    su -s /bin/bash ${HOP3_USER} -c "cd ${CODE_DIR} && bundle exec rake redmine:load_default_data"

    # disable registration with oidc
    [[ -n "${OIDC_ISSUER:-}" ]] && $mysql -e "INSERT INTO settings (name, value, updated_on) VALUES ('self_registration', 0, NOW())"
else
    echo "=> Run database migration"
    export SECRET_KEY_BASE=$(cat "${DATA_DIR}/secrets.yml" | grep 'secret_key_base:' | sed -e "s/.*secret_key_base:\s*//")
    cd "${CODE_DIR}"
    su -s /bin/bash ${HOP3_USER} -c "cd ${CODE_DIR} && bundle exec rake db:migrate"
fi

echo "=> Ensure mail from address"
mail_from="${MAIL_FROM:-noreply@localhost}"
# https://www.redmine.org/issues/5913 . Setting display name will override author name
[[ -n "${MAIL_FROM_DISPLAY_NAME:-}" ]] && mail_from="${MAIL_FROM_DISPLAY_NAME} <${MAIL_FROM}>"
# single quote support in display name
mail_from_base64=$(echo -n "${mail_from}" | base64)
$mysql -e "INSERT INTO settings (name, value) VALUES ('mail_from', FROM_BASE64('${mail_from_base64}')) ON DUPLICATE KEY UPDATE name='mail_from', value=FROM_BASE64('${mail_from_base64}');"

echo "=> Set hostname"
app_domain="${HOP3_APP_DOMAIN:-localhost}"
$mysql -e "INSERT INTO settings (name, value) VALUES ('host_name', '${app_domain}') ON DUPLICATE KEY UPDATE name='host_name', value='${app_domain}';"
$mysql -e "INSERT INTO settings (name, value) VALUES ('protocol', 'https') ON DUPLICATE KEY UPDATE name='protocol', value='https';"

if [[ -n "${OIDC_ISSUER:-}" ]]; then
    echo "=> Update OIDC config"

    # update oidc plugin files
    rm -rf "${DATA_DIR}/plugins/redmine_oauth" && cp -R "${CODE_DIR}/plugins.orig/redmine_oauth" "${DATA_DIR}/plugins/redmine_oauth"

    provider_name=$(php -r "echo addslashes(preg_replace('/[\xf0-\xf7].../s', '', \"${OIDC_PROVIDER_NAME:-SSO}\"));")

    # settings.name has no unique constraint! so, we cannot duplicate key update
    $mysql -e "DELETE FROM settings WHERE name='plugin_redmine_oauth';"
    $mysql -e "INSERT INTO settings (name, value, updated_on) VALUES ( \
            'plugin_redmine_oauth', \
            '--- !ruby/hash:ActiveSupport::HashWithIndifferentAccess\noauth_name: Custom\nbutton_color: \"#ffbe6f\"\nbutton_icon: fas fa-address-card\nsite: \'\'\nclient_id: ${OIDC_CLIENT_ID}\nclient_secret: ${OIDC_CLIENT_SECRET}\ntenant_id: \'\'\ncustom_name: \"${provider_name}\"\ncustom_auth_endpoint: ${OIDC_AUTH_ENDPOINT}\ncustom_token_endpoint: ${OIDC_TOKEN_ENDPOINT}\ncustom_profile_endpoint: ${OIDC_PROFILE_ENDPOINT}\ncustom_scope: openid profile email\ncustom_uid_field: sub\ncustom_email_field: email\nself_registration: \"3\"\n', \
            NOW() )"
fi

echo "=> Migrate plugins"
cd "${CODE_DIR}"
su -s /bin/bash ${HOP3_USER} -c "cd ${CODE_DIR} && bundle exec rake redmine:plugins:migrate"

echo "=> Precompile assets"
su -s /bin/bash ${HOP3_USER} -c "cd ${CODE_DIR} && bundle exec rake assets:precompile"

echo "==> Starting redmine"
exec su -s /bin/bash ${HOP3_USER} -c "cd ${CODE_DIR} && bundle exec rails server -u webrick -e production -b 0.0.0.0"
