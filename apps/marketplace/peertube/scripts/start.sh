#!/bin/bash
# PeerTube start script for Hop3

set -eu

DATA_DIR="${HOP3_DATA_DIR:-/app/data}"
CODE_DIR="${HOP3_CODE_DIR:-/app/code}"
PKG_DIR="${HOP3_PKG_DIR:-/app/pkg}"
HOP3_USER="${HOP3_USER:-www-data}"

mkdir -p "${DATA_DIR}/storage" /run/peertube/cache /run/peertube/npm /tmp/peertube

# do not rely on WORKDIR
cd "${CODE_DIR}/server"

install_oidc() {
    if [[ -n "${OIDC_ISSUER:-}" ]]; then
        echo "==> Installing OIDC plugin"
        npm run plugin:install -- -n peertube-plugin-auth-openid-connect -v ${PEERTUBE_OPENID_PLUGIN_VERSION:-1.0.3}
        update_oidc
    fi
}

update_oidc() {
    echo "==> Updating OIDC config"

    provider_name="${OIDC_PROVIDER_NAME:-SSO}"
    PGPASSWORD=${POSTGRES_PASSWORD:-} psql -h ${POSTGRES_HOST:-localhost} -p ${POSTGRES_PORT:-5432} -U ${POSTGRES_USERNAME:-peertube} -d ${POSTGRES_DATABASE:-peertube} \
        -c "UPDATE plugin SET settings='{\"scope\": \"openid email profile\", \"client-id\": \"${OIDC_CLIENT_ID}\", \"discover-url\": \"${OIDC_DISCOVERY_URL:-${OIDC_ISSUER}/.well-known/openid-configuration}\", \"client-secret\": \"${OIDC_CLIENT_SECRET}\", \"mail-property\": \"email\", \"auth-display-name\": \"${provider_name//\'/\'\'}\", \"username-property\": \"preferred_username\", \"signature-algorithm\": \"RS256\", \"display-name-property\": \"name\"}' WHERE name='auth-openid-connect'"
}

first_time_setup() {
    echo "==> Starting peertube to run migrations on first run"
    npm start &
    sleep 10

    while ! curl --silent --output /dev/null --fail http://localhost:9000/; do
        echo "==> Waiting for peertube"
        sleep 5
    done

    killall -SIGTERM peertube || true
    sleep 5

    echo "==> Reset root password"
    echo "changeme" | npm run reset-password -- -u root
    sleep 5  # the above command seems to spawn a separate process to change password in background

    install_oidc

    echo "==> First time setup complete"
}

update_config() {
    echo "==> Ensure and updating configs"

    # version 5 needs this now
    if [[ $(yq eval '.secrets.peertube' "${DATA_DIR}/production.yaml") == "" ]]; then
        yq eval ".secrets.peertube = \"$(openssl rand -hex 32)\"" -i "${DATA_DIR}/production.yaml"
    fi

    yq eval ".webserver.hostname = \"${HOP3_APP_DOMAIN:-localhost}\"" -i "${DATA_DIR}/production.yaml"

    # database
    yq eval ".database.hostname = \"${POSTGRES_HOST:-localhost}\"" -i "${DATA_DIR}/production.yaml"
    yq eval ".database.port = ${POSTGRES_PORT:-5432}" -i "${DATA_DIR}/production.yaml"
    yq eval ".database.username = \"${POSTGRES_USERNAME:-peertube}\"" -i "${DATA_DIR}/production.yaml"
    yq eval ".database.password = \"${POSTGRES_PASSWORD:-}\"" -i "${DATA_DIR}/production.yaml"
    yq eval ".database.name = \"${POSTGRES_DATABASE:-peertube}\"" -i "${DATA_DIR}/production.yaml"
    yq eval "del(.database.suffix)" -i "${DATA_DIR}/production.yaml"

    # redis
    yq eval ".redis.hostname = \"${REDIS_HOST:-localhost}\"" -i "${DATA_DIR}/production.yaml"
    yq eval ".redis.port = ${REDIS_PORT:-6379}" -i "${DATA_DIR}/production.yaml"
    yq eval ".redis.auth = \"${REDIS_PASSWORD:-}\"" -i "${DATA_DIR}/production.yaml"

    # smtp
    yq eval ".smtp.hostname = \"${SMTP_HOST:-localhost}\"" -i "${DATA_DIR}/production.yaml"
    yq eval ".smtp.port = ${SMTP_PORT:-25}" -i "${DATA_DIR}/production.yaml"
    yq eval ".smtp.username = \"${SMTP_USERNAME:-}\"" -i "${DATA_DIR}/production.yaml"
    yq eval ".smtp.password = \"${SMTP_PASSWORD:-}\"" -i "${DATA_DIR}/production.yaml"
    yq eval ".smtp.tls = false" -i "${DATA_DIR}/production.yaml"
    yq eval ".smtp.disable_starttls = true" -i "${DATA_DIR}/production.yaml"
    yq eval ".smtp.from_address = \"${MAIL_FROM:-noreply@localhost}\"" -i "${DATA_DIR}/production.yaml"

    # ensure settings which were later added
    yq eval ".storage.bin = \"${DATA_DIR}/storage/bin/\"" -i "${DATA_DIR}/production.yaml"
    yq eval ".storage.well_known = \"${DATA_DIR}/storage/well_known/\"" -i "${DATA_DIR}/production.yaml"
    yq eval ".storage.tmp_persistent = \"${DATA_DIR}/storage/tmp_persistent/\"" -i "${DATA_DIR}/production.yaml"
    yq eval ".storage.well_known = \"${DATA_DIR}/storage/well-known/\"" -i "${DATA_DIR}/production.yaml"
    yq eval ".storage.uploads = \"${DATA_DIR}/storage/uploads/\"" -i "${DATA_DIR}/production.yaml"
    yq eval ".storage.client_overrides = \"${DATA_DIR}/storage/client-overrides/\"" -i "${DATA_DIR}/production.yaml"
    if [[ $(yq eval '.static_files.private_files_require_auth' "${DATA_DIR}/production.yaml") == "" ]]; then
        yq eval ".static_files.private_files_require_auth = true" -i "${DATA_DIR}/production.yaml"
    fi

    yq eval ".storage.storyboards = \"${DATA_DIR}/storage/storyboards/\"" -i "${DATA_DIR}/production.yaml"
    if [[ -d "${DATA_DIR}/storage/videos" ]]; then
        echo "==> Migrate videos/ to web-videos/"
        mv "${DATA_DIR}/storage/videos" "${DATA_DIR}/storage/web-videos"
    fi
    yq eval ".storage.web_videos = \"${DATA_DIR}/storage/web-videos/\"" -i "${DATA_DIR}/production.yaml"
    yq eval "del(.storage.videos)" -i "${DATA_DIR}/production.yaml"
    yq eval "del(.transcoding.webtorrent)" -i "${DATA_DIR}/production.yaml"
    yq eval ".transcoding.web_videos.enabled = true" -i "${DATA_DIR}/production.yaml"

    yq eval ".storage.original_video_files = \"${DATA_DIR}/storage/original_video_files/\"" -i "${DATA_DIR}/production.yaml"
}

echo "==> Changing ownership"
chown -R ${HOP3_USER}:${HOP3_USER} "${DATA_DIR}" /run/peertube /tmp/peertube

# Set eviction policy to prevent warnings
while ! REDISCLI_AUTH="${REDIS_PASSWORD:-}" redis-cli -h "${REDIS_HOST:-localhost}" -p "${REDIS_PORT:-6379}" ping >/dev/null 2>&1; do
    echo "==> Waiting for redis"
    sleep 5
done
REDISCLI_AUTH="${REDIS_PASSWORD:-}" redis-cli -h "${REDIS_HOST:-localhost}" -p "${REDIS_PORT:-6379}" CONFIG SET maxmemory-policy noeviction

if [[ ! -f "${DATA_DIR}/production.yaml" ]]; then
    echo "==> First run. creating config"
    cp "${PKG_DIR}/templates/production.yaml.template" "${DATA_DIR}/production.yaml"

    update_config
    first_time_setup
else
    update_config
    if [[ -n "${OIDC_ISSUER:-}" ]]; then
        install_oidc
        update_oidc
    fi
fi

echo "==> Configuring nginx"
cp "${PKG_DIR}/conf/nginx.conf" /run/peertube-nginx.conf

echo "==> Starting PeerTube"
exec /usr/bin/supervisord --configuration /etc/supervisor/supervisord.conf --nodaemon -i PeerTube
