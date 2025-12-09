#!/bin/bash
# Taiga start script for Hop3

# set -eu -o pipefail

CODE_DIR="${HOP3_CODE_DIR:-/app/code}"
DATA_DIR="${HOP3_DATA_DIR:-/app/data}"
PKG_DIR="${HOP3_PKG_DIR:-/app/pkg}"
HOP3_USER="${HOP3_USER:-www-data}"

mkdir -p "${DATA_DIR}/media" /run/nginx /run/client_body /run/proxy_temp /run/fastcgi_temp /run/scgi_temp /run/uwsgi_temp

# Setup symlinks
ln -sf "${DATA_DIR}/media" "${CODE_DIR}/taiga-back/media"
ln -sf /run/nginx /var/log/nginx
ln -sf "${DATA_DIR}/conf.json" "${CODE_DIR}/taiga-front-dist/dist/conf.json"

# Copy local.py config
cp "${PKG_DIR}/templates/local.py" "${CODE_DIR}/taiga-back/settings/config.py"

# Will be included in local.py
if [[ ! -f "${DATA_DIR}/customlocal.py" ]]; then
    echo -e "# Place custom local.py settings in this file\n" > "${DATA_DIR}/customlocal.py"
fi

# Create and merge any user conf.json
if [[ ! -f "${DATA_DIR}/conf.json" ]]; then
    echo "{}" > "${DATA_DIR}/conf.json"
fi

if [[ -n "${LDAP_HOST:-}" ]]; then
    echo "=> Update conf.json with LDAP"
    node "${PKG_DIR}/conf/json-merge.js" "${DATA_DIR}/conf.json" "${PKG_DIR}/templates/conf_ldap.json"
else
    echo "=> Update conf.json"
    node "${PKG_DIR}/conf/json-merge.js" "${DATA_DIR}/conf.json" "${PKG_DIR}/templates/conf.json"
fi

"${CODE_DIR}/node_modules/.bin/json" -I -f "${DATA_DIR}/conf.json" -e "this.api = '${HOP3_APP_ORIGIN:-http://localhost:8000}/api/v1/'"

echo "=> Update nginx.conf"
sed -e "s,##APP_DOMAIN##,${HOP3_APP_DOMAIN:-localhost}," "${PKG_DIR}/conf/nginx.conf" > /run/nginx.conf

echo "=> Setup taiga virtual env"
source "${CODE_DIR}/venv/bin/activate"

export DJANGO_SETTINGS_MODULE=settings.config

cd "${CODE_DIR}/taiga-back"

if [[ ! -d "${DATA_DIR}/media/user" ]]; then
    echo "=> New installation create initial project templates"

    echo "=> Run migration scripts"
    mkdir -p "${DATA_DIR}/media/user"

    python3.11 manage.py migrate --noinput
    python3.11 manage.py loaddata initial_user
    python3.11 manage.py loaddata initial_project_templates
else
    echo "=> Run migration scripts"
    python3.11 manage.py migrate --noinput
fi

echo "=> Make hop3 user own /run"
chown -R ${HOP3_USER}:${HOP3_USER} /run
chown -R ${HOP3_USER}:${HOP3_USER} "${DATA_DIR}"

echo "=> Start nginx"
nginx -c /run/nginx.conf &

echo "=> Start taiga-back"
export HOME="${CODE_DIR}"

cd "${CODE_DIR}/taiga-back"

# Calculate worker count based on available memory
memory_limit=$(cat /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null || echo "314572800")
worker_count=$((memory_limit/1024/1024/150)) # 1 worker for 150M
worker_count=$((worker_count > 8 ? 8 : worker_count)) # max of 8
worker_count=$((worker_count < 1 ? 1 : worker_count)) # min of 1

echo "Starting gunicorn with ${worker_count} workers"
exec su -s /bin/bash ${HOP3_USER} -c "source ${CODE_DIR}/venv/bin/activate && gunicorn -w ${worker_count} -t 60 --pythonpath=. -b 127.0.0.1:8001 taiga.wsgi"
