#!/usr/bin/env bash
# Run the read-only benchmark tier against a live host and record each probe.
#
# Non-destructive by construction: every probe here only reads /proc and
# cgroups, builds Nix packages into the store, or inspects Docker images. It is
# therefore safe against a box that is in use, which is what distinguishes it
# from the deploy tier (`hop3-bench matrix`), which OS-rebuilds its target.
#
# Covers G3 (disk / dedup), G5 (closure vs image, update delta), G6
# (reproducibility) and the control-plane half of G4. The build-and-install
# timings of G1 are NOT here — those need a blank slate.
#
# Usage: readonly-tier.sh <host> [outfile]

set -uo pipefail

HOST="${1:?usage: readonly-tier.sh <host> [outfile]}"
OUT="${2:-notes/benchmarks/$(date +%F)-readonly.jsonl}"

# The six applications of paper Table 3 (Go + Java), so the refreshed numbers
# are directly comparable with the run they replace.
APPS=(miniflux vikunja mattermost gitea forgejo keycloak)

mkdir -p "$(dirname "$OUT")"

# Each probe is recorded with its own name and the raw JSON it produced, so a
# partial run is still usable and a failed probe is visible rather than absent.
record() {
  local probe="$1"; shift
  echo "--> $probe" >&2
  local started ok out
  started="$(date -u +%FT%TZ)"
  if out="$(uv run hop3-bench "$probe" --ssh "$HOST" "$@" 2>&1)"; then ok=true; else ok=false; fi
  python3 - "$OUT" "$probe" "$started" "$ok" "$out" <<'PY'
import json, sys
out_path, probe, started, ok, raw = sys.argv[1:6]
try:
    payload = json.loads(raw.strip().splitlines()[-1])
except Exception:
    payload = None
with open(out_path, "a") as f:
    f.write(json.dumps({
        "probe": probe, "started": started, "ok": ok == "true",
        "result": payload, "raw": None if payload else raw[-4000:],
    }) + "\n")
PY
  [ "$ok" = true ] || echo "    FAILED (recorded)" >&2
}

echo "read-only tier against $HOST -> $OUT" >&2

record memory
record cgroup-memory hop3-server hop3-rootd
record closures "${APPS[@]}"
record update-delta "${APPS[@]}"
# Rebuild-and-compare is the slowest probe; it runs last so everything cheaper
# is already on disk if the run is interrupted.
record reproducibility "${APPS[@]}"

echo "done -> $OUT" >&2
