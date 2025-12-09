#!/bin/bash
# Cal.com start script for Hop3

set -eu

DATA_DIR="${HOP3_DATA_DIR:-/app/data}"
CODE_DIR="${HOP3_CODE_DIR:-/app/code}"
HOP3_USER="${HOP3_USER:-www-data}"

echo "=> Creating directories"
mkdir -p "${DATA_DIR}" /run/calcom /run/yarn /run/cache /run/calcom/.turbo

APP_BASEDIR="${CODE_DIR}/calcom"

# Generate secrets if not exist
if [[ ! -f "${DATA_DIR}/.nextauth_secret" ]]; then
    echo "==> Create NEXTAUTH secret"
    openssl rand -base64 32 > "${DATA_DIR}/.nextauth_secret"
fi

if [[ ! -f "${DATA_DIR}/.jwt_secret" ]]; then
    echo "==> Generate initial app jwt_secret"
    openssl rand -hex 24 > "${DATA_DIR}/.jwt_secret"
fi

if [[ ! -f "${DATA_DIR}/.calendso_encryption_key" ]]; then
    echo "==> Create CALENDSO encryption key"
    openssl rand -base64 24 > "${DATA_DIR}/.calendso_encryption_key"
fi

# Generate VAPID keys
npx web-push generate-vapid-keys --json > /run/calcom/vapid-keys
NEXT_PUBLIC_VAPID_PUBLIC_KEY=$(cat /run/calcom/vapid-keys | jq -r .publicKey)
VAPID_PRIVATE_KEY=$(cat /run/calcom/vapid-keys | jq -r .privateKey)

if [[ ! -f "${DATA_DIR}/env" ]]; then
    cat > "${DATA_DIR}/env" << EOF
# Add custom environment variables in this file
NEXT_PUBLIC_LICENSE_CONSENT=true
CALCOM_TELEMETRY_DISABLED=true
NEXT_PUBLIC_SENTRY_DSN=
CALCOM_LICENSE_KEY=
API_KEY_PREFIX=cal_
IS_SELF_HOSTED=true
EOF
fi

export DATABASE_URL="postgres://${POSTGRES_USERNAME:-calcom}:${POSTGRES_PASSWORD:-}@${POSTGRES_HOST:-localhost}:${POSTGRES_PORT:-5432}/${POSTGRES_DATABASE:-calcom}"
export DATABASE_DIRECT_URL="${DATABASE_URL}"
export NEXTAUTH_SECRET="$(cat ${DATA_DIR}/.nextauth_secret)"
export JWT_SECRET="$(cat ${DATA_DIR}/.jwt_secret)"
export CALENDSO_ENCRYPTION_KEY="$(cat ${DATA_DIR}/.calendso_encryption_key)"

echo "=> Merge configs"
cat "${DATA_DIR}/env" > /run/calcom/.env
cat >> /run/calcom/.env << EOF
NEXTAUTH_SECRET="${NEXTAUTH_SECRET}"
CALENDSO_ENCRYPTION_KEY="${CALENDSO_ENCRYPTION_KEY}"
DATABASE_URL="${DATABASE_URL}"
EMAIL_FROM="${MAIL_FROM:-noreply@localhost}"
EMAIL_FROM_NAME="${MAIL_FROM_DISPLAY_NAME:-Cal.com}"
EMAIL_SERVER_HOST="${SMTP_HOST:-localhost}"
EMAIL_SERVER_PORT="${SMTP_PORT:-25}"
EMAIL_SERVER_USER="${SMTP_USERNAME:-}"
EMAIL_SERVER_PASSWORD="${SMTP_PASSWORD:-}"
NEXT_PUBLIC_WEBAPP_URL="${HOP3_APP_ORIGIN:-http://localhost:3000}"
REDIS_URL="redis://:${REDIS_PASSWORD:-}@${REDIS_HOST:-localhost}:${REDIS_PORT:-6379}"
NEXT_PUBLIC_VAPID_PUBLIC_KEY=${NEXT_PUBLIC_VAPID_PUBLIC_KEY}
VAPID_PRIVATE_KEY=${VAPID_PRIVATE_KEY}
EOF

# Setup symlinks
ln -sf /run/calcom/.env "${APP_BASEDIR}/.env"
ln -sf /run/calcom/.turbo "${APP_BASEDIR}/.turbo"
ln -sf /run/calcom/.env "${APP_BASEDIR}/apps/api/v2/.env"

echo "==> Migrate DB"
cd "${APP_BASEDIR}" && npx prisma migrate deploy

chown -R ${HOP3_USER}:${HOP3_USER} "${DATA_DIR}" /run/calcom

echo "==> Starting Cal.com"
exec /usr/bin/supervisord --configuration /etc/supervisor/supervisord.conf --nodaemon -i Cal.com
