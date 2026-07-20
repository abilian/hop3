#!/usr/bin/env bash
# Create or delete a throwaway benchmark box (Hetzner). Prints the IPv4 on create.
#
#   provision.sh create <name> [type] [location]
#   provision.sh delete <name>
#
# Requires: hcloud CLI, HETZNER_API_TOKEN, and HETZNER_SSH_KEY_NAME.
set -euo pipefail

action=${1:?usage: provision.sh create|delete <name> [type] [location]}
name=${2:?missing box name}
type=${3:-cpx41}          # 8 vCPU / 16 GB x86 — the class the paper reports
location=${4:-hil}
: "${HETZNER_SSH_KEY_NAME:?set HETZNER_SSH_KEY_NAME}"

case "$action" in
  create)
    hcloud server create --name "$name" --type "$type" --image ubuntu-24.04 \
      --ssh-key "$HETZNER_SSH_KEY_NAME" --location "$location" >/dev/null
    ip=$(hcloud server ip "$name")
    # a reused IP trips host-key checking; drop any stale entry
    ssh-keygen -R "$ip" >/dev/null 2>&1 || true
    for _ in $(seq 1 25); do
      ssh -o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout=8 \
        "root@$ip" true 2>/dev/null && break
      sleep 8
    done
    echo "$ip"
    ;;
  delete)
    hcloud server delete "$name"
    ;;
  *)
    echo "unknown action: $action" >&2; exit 2 ;;
esac
