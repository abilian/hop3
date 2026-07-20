#!/usr/bin/env bash
# Install Hop3 on a fresh box ready for the matrix run.
# Sets OPERATOR_EMAIL — without it every ADR-056 admin-bootstrap app fails to deploy.
#   matrix-setup.sh <host>
set -euo pipefail
host=${1:?usage: matrix-setup.sh <host>}
uv run hop3-deploy-server --host "$host" --user root --from local --clean --with all
ssh -o BatchMode=yes -o StrictHostKeyChecking=no "root@$host" '
  grep -q "^OPERATOR_EMAIL" /home/hop3/hop3-server.toml \
    || sed -i "1i OPERATOR_EMAIL = \"bench@hop3.example\"" /home/hop3/hop3-server.toml
  systemctl restart hop3-server; sleep 5; systemctl is-active hop3-server'
