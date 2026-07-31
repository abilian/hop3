#!/usr/bin/env bash
# Measure the control plane on a genuinely cold box, then again with one app.
#
# Why this is a script and not two commands: the figure it exists to produce is
# only meaningful in the seconds after install, before anything warms the page
# cache. On 2026-07-28 the same cgroup metric read 185 MB in the paper and
# 1139 MB on the long-lived dev host — 914 MB of that difference was page cache
# (`memory.stat` file accounting), not process memory. So this records BOTH the
# stable metric (PSS) and the cache-charging one (cgroup memory.current) with
# its anon/file breakdown, at a known point in the box's life.
#
# Run IMMEDIATELY after `hop3-deploy-server --provider hetzner --clean`, before
# deploying anything.
#
# Usage: fresh-box-memory.sh <host> [outfile]

set -uo pipefail

HOST="${1:?usage: fresh-box-memory.sh <host> [outfile]}"
OUT="${2:-notes/benchmarks/$(date +%F)-freshbox-memory.jsonl}"
SVC=/sys/fs/cgroup/system.slice/hop3-server.service

mkdir -p "$(dirname "$OUT")"

sample() {
  local label="$1"
  echo "--> sampling: $label" >&2
  local pss cg
  pss="$(uv run hop3-bench memory --ssh "$HOST" 2>&1 | tail -1)"
  # anon is the process's own memory; file is page cache the cgroup is charged
  # for. Reporting memory.current without this split is what made the published
  # figure unreproducible.
  cg="$(ssh -o BatchMode=yes "root@$HOST" \
        "cat $SVC/memory.current 2>/dev/null; grep -E '^(anon|file|slab) ' $SVC/memory.stat 2>/dev/null" 2>&1)"
  python3 - "$OUT" "$label" "$pss" "$cg" <<'PY'
import json, sys
out, label, pss_raw, cg_raw = sys.argv[1:5]
try:
    pss = json.loads(pss_raw)
except Exception:
    pss = {"unparsed": pss_raw[-500:]}
cg, lines = {}, [l for l in cg_raw.splitlines() if l.strip()]
if lines and lines[0].strip().isdigit():
    cg["current_mb"] = round(int(lines[0]) / 1e6, 1)
for l in lines[1:]:
    parts = l.split()
    if len(parts) == 2 and parts[1].isdigit():
        cg[parts[0] + "_mb"] = round(int(parts[1]) / 1e6, 1)
rec = {"label": label, "pss": pss, "cgroup": cg}
with open(out, "a") as f:
    f.write(json.dumps(rec) + "\n")
print(f"    PSS={pss.get('pss_mb','?')} MB  cgroup.current={cg.get('current_mb','?')} MB "
      f"(anon={cg.get('anon_mb','?')} file={cg.get('file_mb','?')})", file=sys.stderr)
PY
}

echo "fresh-box control-plane memory on $HOST -> $OUT" >&2
sample "0-apps-cold"

echo >&2
echo "Now deploy ONE app, then re-run:  $0 $HOST $OUT" >&2
echo "(the second invocation appends; label it by hand in the file if needed)" >&2
