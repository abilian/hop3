#!/usr/bin/env bash
# The 20x4 matrix: deploy every golden app in every variant, timing each cell.
#
#   matrix-run.sh <host> <logdir> [variant...]      # default: all four variants
#
# Emits one JSON line per cell to stdout. A failing cell keeps its FULL deploy
# log at <logdir>/<variant>-<app>.log and the JSON carries the extracted reason:
# a failure whose cause was discarded is a silent skip, and the per-variant
# failure reasons are the point of the exercise (they are the platform backlog).
#
# Assumes Hop3 is ALREADY installed on <host> (see matrix-setup.sh).
set -uo pipefail
host=${1:?usage: matrix-run.sh <host> <logdir> [variant...]}
logdir=${2:?usage: matrix-run.sh <host> <logdir> [variant...]}
shift 2
variants=("$@"); [ ${#variants[@]} -gt 0 ] || variants=(native docker nix nix-gen)
mkdir -p "$logdir"

# golden-20-balanced (rebalanced 2026-07-21): PHP 5 / Go 5 / Python 4 / Node 3 /
# JVM 3. Ruby (0 native/nix today) is packaged in parallel and folds in later.
GOLDEN="wordpress nextcloud bookstack invoice-ninja matomo
gitea miniflux vikunja gatus owncast
bugsink isso radicale searxng
directus wiki-js etherpad
stirling-pdf keycloak jenkins"

# Pull a one-line cause out of a deploy log; never return empty.
reason_from() {
  local log=$1 line
  line=$(grep -m1 -oE 'ERROR: deploying app failed: .*|Deploy failed: [^|]*|build-failure[^ ]*|No such file[^"]*|command not found[^"]*' "$log" 2>/dev/null | head -1)
  [ -n "$line" ] || line=$(grep -m1 -iE 'error|failed|timeout' "$log" 2>/dev/null | head -1)
  [ -n "$line" ] || line="no diagnostic in log"
  echo "$line" | tr -d '"\\' | cut -c1-200
}

for v in "${variants[@]}"; do
  for app in $GOLDEN; do
    path="apps/real-apps-$v/$app"
    if [ ! -f "$path/hop3.toml" ]; then
      printf '{"app":"%s","variant":"%s","status":"no-recipe"}\n' "$app" "$v"
      continue
    fi
    log="$logdir/$v-$app.log"
    t0=$(date +%s)
    uv run hop3-test run --host "$host" "$path" >"$log" 2>&1
    rc=$?
    t1=$(date +%s)
    if [ $rc -eq 0 ]; then
      printf '{"app":"%s","variant":"%s","seconds":%s,"rc":0,"status":"ok"}\n' \
        "$app" "$v" "$((t1 - t0))"
      rm -f "$log"          # keep only failures; successes are the timing itself
    else
      printf '{"app":"%s","variant":"%s","seconds":%s,"rc":%s,"status":"failed","reason":"%s","log":"%s"}\n' \
        "$app" "$v" "$((t1 - t0))" "$rc" "$(reason_from "$log")" "$log"
    fi
  done
done
