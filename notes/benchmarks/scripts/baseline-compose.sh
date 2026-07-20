#!/usr/bin/env bash
# Install Docker on a fresh box and measure dockerd's control plane.
#   baseline-compose.sh <host>
set -euo pipefail
host=${1:?usage: baseline-compose.sh <host>}
S() { ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=12 "root@$host" "$@"; }

S 'export DEBIAN_FRONTEND=noninteractive
   apt-get update -qq && apt-get install -y -qq docker.io docker-compose-v2
   systemctl enable --now docker' >/dev/null
sleep 20
echo "--- dockerd idle ---"
uv run hop3-bench cgroup-memory --ssh "$host" docker

S 'docker run -d --name web -p 8080:80 nginx >/dev/null 2>&1 || true; sleep 12'
echo "--- dockerd + 1 container ---"
uv run hop3-bench cgroup-memory --ssh "$host" docker
