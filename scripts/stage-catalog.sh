#!/usr/bin/env bash
#
# stage-catalog.sh — drive the app-catalog staging loop end to end
# (see docs/src/developers/catalog-staging.md).
#
# Automates: keygen -> publish (build + minisign-sign) -> upload to the box ->
# sideload (verify the signature + publish the catalog directly on the box, no
# HTTP) -> reload the server -> list -> install --app -> destroy.
#
# Why sideload instead of the HTTPS fetch path? `hop3 catalog refresh` is the
# PRODUCTION path: the server fetches a signed tarball from a remote URL over
# CA-trusted HTTPS. For a self-test the tarball is already on the box, so we call
# the same verify+publish routine (`install_catalog_tarball`) directly — the
# minisign signature is still checked against your key; only the (locally
# pointless) HTTP transport + TLS trust setup is skipped. No baked-in key, no
# nginx, no firewall changes.
#
# The producer half (keygen/publish) and the CLI half (list/install/destroy) are
# portable and tested. The box half runs over `ssh $REMOTE` and assumes a
# standard Hop3 install (hop3 venv at /home/hop3/venv, service env in
# /etc/default/hop3, catalog under $HOP3_ROOT/catalog owned by the hop3 user).
#
# Usage:
#   scripts/stage-catalog.sh setup                 # deploy code + publish + sideload + list
#   scripts/stage-catalog.sh publish               # re-sign + upload + sideload (the iteration loop)
#   scripts/stage-catalog.sh list
#   scripts/stage-catalog.sh install <blueprint-id> <app-name>
#   scripts/stage-catalog.sh destroy <app-name>
#   scripts/stage-catalog.sh deploy                # redeploy server code only (no catalog work)
#   scripts/stage-catalog.sh all <blueprint-id> <app-name>   # setup + install
#
# Override any of these via the environment:
set -euo pipefail

HOST="${HOST:-hop3-dev.abilian.com}"
REMOTE="${REMOTE:-root@${HOST}}"
CATALOG_REPO="${CATALOG_REPO:-${HOME}/projects/hop3/hop3-catalog}"
HOP3_REPO="${HOP3_REPO:-${HOME}/projects/hop3/hop3}"
APPS_DIR="${APPS_DIR:-${CATALOG_REPO}/apps}"
KEY_DIR="${KEY_DIR:-${CATALOG_REPO}/keys}"
DIST_DIR="${DIST_DIR:-${CATALOG_REPO}/dist}"
REMOTE_DIR="${REMOTE_DIR:-/home/hop3/catalog-staging}"
HOP3="${HOP3:-hop3}"                      # local CLI, configured to talk to the box

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
run_hop3catalog() { (cd "${HOP3_REPO}/packages/hop3-server" && uv run hop3-catalog "$@"); }

keygen() {
  if [[ -f "${KEY_DIR}/catalog.key" ]]; then
    say "keygen: reusing existing keypair in ${KEY_DIR}"
  else
    say "keygen: generating catalog keypair in ${KEY_DIR}"
    run_hop3catalog keygen --out-dir "${KEY_DIR}"
  fi
}

deploy() {
  say "deploy: hop3-deploy-server --from local --host ${HOST}"
  (cd "${HOP3_REPO}" && hop3-deploy-server --from local --host "${HOST}")
}

publish() {
  keygen
  local serial; serial="$(date +%s)"     # monotonic across republishes (anti-rollback)
  say "publish: building + signing catalog (serial ${serial})"
  run_hop3catalog validate "${APPS_DIR}"
  run_hop3catalog publish "${APPS_DIR}" --key "${KEY_DIR}/catalog.key" \
    --out-dir "${DIST_DIR}" --serial "${serial}"
  say "publish: uploading tarball + signature + pubkey to ${REMOTE}:${REMOTE_DIR}/"
  ssh "${REMOTE}" "mkdir -p ${REMOTE_DIR}"
  scp "${DIST_DIR}/catalog.tar.gz" "${DIST_DIR}/catalog.tar.gz.minisig" \
    "${KEY_DIR}/catalog.pub" "${REMOTE}:${REMOTE_DIR}/"
}

sideload() {
  say "sideload: verify the signature + publish the catalog directly on the box, then reload the server"
  ssh "${REMOTE}" bash -seu -- "${REMOTE_DIR}" <<'EOF'
remote_dir="$1"
# Verify + publish as the hop3 user (owns $HOP3_ROOT/catalog). Source the service
# env first so config.CATALOG_ROOT resolves exactly as the running server sees it.
cat > /tmp/hop3-sideload.py <<'PY'
import sys
from pathlib import Path
from hop3.config import config
from hop3.server.catalog.sync import install_catalog_tarball

d = Path(sys.argv[1])
result = install_catalog_tarball(
    d / "catalog.tar.gz",
    (d / "catalog.tar.gz.minisig").read_text(),
    (d / "catalog.pub").read_text(),
    config.CATALOG_ROOT,
    config.CATALOG_STATE_ROOT,
)
if result.changed:
    print(f"installed catalog serial {result.serial} at {config.CATALOG_ROOT}")
else:
    # Re-publishing without bumping the serial: nothing to install, and nothing
    # wrong -- but say so, or the loop looks like it worked when it did nothing.
    print(
        f"catalog serial {result.serial} was already installed -- nothing changed. "
        "Re-run `publish` (its serial is the current time, so it will increase)."
    )
PY
chown hop3:hop3 /tmp/hop3-sideload.py
su - hop3 -c "set -a; . /etc/default/hop3 2>/dev/null; /home/hop3/venv/bin/python /tmp/hop3-sideload.py '$remote_dir'"
rm -f /tmp/hop3-sideload.py
# The running server caches its catalog snapshot; restart so it reloads from disk.
systemctl restart hop3-server
for _ in $(seq 1 60); do
  # curl -w prints "000" (not empty) on a connection failure, and `|| true`
  # keeps that "000" (NOT "000000") while satisfying `set -e`.
  code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/ 2>/dev/null || true)
  [ -n "$code" ] && [ "$code" != "000" ] && { echo "hop3-server ready (HTTP $code)"; exit 0; }
  sleep 1
done
echo "WARNING: hop3-server did not respond within 60s after restart" >&2
EOF
}

catalog_list() { say "list"; "${HOP3}" catalog list; }

install() {
  local id="${1:?usage: install <blueprint-id> <app-name>}" name="${2:?}"
  say "install: ${id} as ${name}"
  "${HOP3}" catalog install "${id}" --app "${name}"
  "${HOP3}" app status --app "${name}" || true
}

destroy() {
  local name="${1:?usage: destroy <app-name>}"
  say "destroy: ${name}"
  "${HOP3}" app destroy --app "${name}" -y
}

setup() { deploy; publish; sideload; catalog_list; }

teardown() {
  # Remove the unused HTTPS-hosting leftovers (an earlier version of this script
  # served the catalog over nginx:8443 before switching to sideload). Harmless if
  # already gone. Does not touch installed apps or the published catalog.
  say "teardown: removing unused HTTPS-hosting leftovers on ${REMOTE}"
  ssh "${REMOTE}" bash -seu -- "${REMOTE_DIR}" <<'EOF'
remote_dir="$1"
rm -f /home/hop3/nginx/catalog-staging.conf
rm -f /usr/local/share/ca-certificates/hop3-catalog-staging.crt
update-ca-certificates --fresh >/dev/null 2>&1 || true
sed -i '/^CATALOG_SOURCE_URL=/d' /etc/default/hop3 2>/dev/null || true
rm -f "$remote_dir"/tls.key "$remote_dir"/tls.crt
nginx -t >/dev/null 2>&1 && systemctl reload nginx || true
EOF
}

cmd="${1:-}"; shift || true
case "${cmd}" in
  keygen)   keygen ;;
  deploy)   deploy ;;
  publish)  publish; sideload ;;
  sideload) sideload ;;
  list)     catalog_list ;;
  install)  install "$@" ;;
  destroy)  destroy "$@" ;;
  teardown) teardown ;;
  setup)    setup ;;
  all)      setup; install "$@" ;;
  *) echo "usage: $0 {setup|publish|list|install <id> <name>|destroy <name>|deploy|teardown|all <id> <name>}" >&2; exit 2 ;;
esac
