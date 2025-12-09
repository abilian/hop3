#!/bin/bash
# Radicale start script for Hop3

set -eu -o pipefail

CODE_DIR="${HOP3_CODE_DIR:-/app/code}"
DATA_DIR="${HOP3_DATA_DIR:-/app/data}"
PKG_DIR="${HOP3_PKG_DIR:-/app/pkg}"
HOP3_USER="${HOP3_USER:-www-data}"

cd "${CODE_DIR}"
source "${CODE_DIR}/venv/bin/activate"

mkdir -p "${DATA_DIR}/collections"

echo "==> Update radicale config"
sed -e "s/ldap_uri = ldap:\/\/.*/ldap_uri = ldap:\/\/${LDAP_HOST:-localhost}:${LDAP_PORT:-389}/" \
    -e "s/ldap_base = .*/ldap_base = ${LDAP_USERS_BASE_DN:-ou=users,dc=example}/" \
    -e "s/ldap_reader_dn = .*/ldap_reader_dn = ${LDAP_BIND_DN:-}/" \
    -e "s/ldap_secret = .*/ldap_secret = ${LDAP_BIND_PASSWORD:-}/" \
    "${PKG_DIR}/conf/config" > "/run/config"

if [[ ! -f "${DATA_DIR}/rights" ]]; then
    echo "==> Copy default /app/data/rights file"
    cp "${PKG_DIR}/templates/rights.template" "${DATA_DIR}/rights"
fi

echo "==> Ensure folder permissions"
chown -R ${HOP3_USER}:${HOP3_USER} "${DATA_DIR}"

echo "==> Start radicale"
exec su -s /bin/bash ${HOP3_USER} -c "source ${CODE_DIR}/venv/bin/activate && radicale --config /run/config"
