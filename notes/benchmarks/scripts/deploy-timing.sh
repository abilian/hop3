#!/usr/bin/env bash
# G1: time build-and-install of each app on a target, emitting one JSON line each.
# The first app may carry --clean to install Hop3 itself (cold-install figure).
#
#   deploy-timing.sh <host> <app-path> [more app-paths...]
#
# Each figure covers a full hop3-test cycle (cached toolchain re-provision check,
# build, deploy, HTTP verify, teardown) and so bounds deploy cost from above.
set -uo pipefail
host=${1:?usage: deploy-timing.sh <host> <app-path>...}; shift
[ $# -gt 0 ] || { echo "no apps given" >&2; exit 2; }

for app in "$@"; do
  t0=$(date +%s)
  uv run hop3-test run --host "$host" "$app" >/dev/null 2>&1
  rc=$?
  t1=$(date +%s)
  printf '{"app":"%s","seconds":%s,"rc":%s}\n' "$app" "$((t1 - t0))" "$rc"
done
