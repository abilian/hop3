#!/usr/bin/env bash
# Install a LEAN K3s (addons off) on a fresh box and measure its control plane.
# Measurement uses `hop3-bench cgroup-memory` so every stack shares one metric.
#
#   baseline-k3s.sh <host>
set -euo pipefail
host=${1:?usage: baseline-k3s.sh <host>}
S() { ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=12 "root@$host" "$@"; }

S 'curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--disable traefik --disable servicelb --disable metrics-server" sh -' >/dev/null
S 'for i in $(seq 1 40); do k3s kubectl get nodes 2>/dev/null | grep -q " Ready" && break; sleep 5; done'
sleep 60   # settle
echo "--- k3s idle ---"
uv run hop3-bench cgroup-memory --ssh "$host" k3s
S 'free -m | awk "/Mem:/{print \"system RAM used: \" \$3 \" MB\"}"'

S 'k3s kubectl create deployment web --image=nginx --replicas=1 >/dev/null 2>&1 || true
   for i in $(seq 1 30); do k3s kubectl get pods 2>/dev/null | grep -q Running && break; sleep 5; done'
sleep 20
echo "--- k3s + 1 pod ---"
uv run hop3-bench cgroup-memory --ssh "$host" k3s
