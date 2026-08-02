# Hop3 benchmarks — how to run them

This directory holds the paper's quantitative evaluation: the protocol (`protocol.yaml`), the raw measurement runs (`*.json`), the orchestration scripts (`scripts/`), and this guide. The measurement code is the **`hop3-bench`** harness in the `hop3-tooling` package (`packages/hop3-tooling/src/hop3_tooling/bench/`).

The benchmark set (G1–G10) is specified in `notes/reports/paper-completion-plan.md` §3; the methodology (pinning, PSS/cgroup mechanics, the like-for-like Nix-vs-Docker boundary, threats to validity) is in [`../reports/TR-03.md`](../reports/TR-03.md) §6.4. This README is the operator's runbook.

**Every figure quoted in the paper comes from `hop3-bench report`.** No number is hand-transcribed; each traces to the run that produced it.

## Two tiers, one safety rule

- **Read-only / direct-build tier** (memory, closures, disk, reproducibility, update delta) — non-destructive. Safe against a live box; it only reads `/proc` and cgroups, builds Nix packages into the store, and inspects Docker images.
- **Deploy tier** (build-and-install timing, baselines) — **mutates the target** and needs a *cold* store for honest "from scratch" numbers. Run only on the **dedicated bench box**, blank-slated by an OS rebuild — never on a shared server.

Every probe is **fail-loud**: it raises on a missing tool, an empty process set, or unparsable output rather than reporting a zero. A swallowed probe is a fake data point.

## Prerequisites

- `uv` — the harness runs via `uv run hop3-bench`.
- A **Linux target** with `nix` (flakes enabled) and `docker`.
- **Passwordless SSH** as `root` (`ssh -o BatchMode=yes`). Test: `ssh root@<host> true`.
- For the deploy tier: the `hcloud` CLI, `HETZNER_API_TOKEN`, and `HETZNER_SERVER_ID` (the one dedicated bench box). No SSH-key name is needed — a box is never created, only rebuilt.

Nix builds are Linux-targeted, so build/closure measurements must run **on the Linux target** (via `--ssh`), not locally on macOS.

## Regenerating the paper's figures

```bash
uv run hop3-bench report                                   # default: the latest run
uv run hop3-bench report --results notes/benchmarks/<run>.json
```

This emits the closure table (report Table 7), the deduplication sentence, the build-and-install band, and the control-plane baseline comparison — exactly as they appear in §6.4.

## Measurement commands

| Command | Measures | Paper section |
|---------|----------|---------------|
| `memory --ssh H` | control-plane PSS + RSS of `hop3-server` | §6.2, §6.4 |
| `cgroup-memory --ssh H SERVICE...` | cgroup `memory.current` — the cross-stack metric | §6.4 baselines |
| `closures --ssh H APP...` | Nix closure size, path count, and dedup union | §6.4 Table 7 |
| `docker-size --ssh H IMAGE...` | uncompressed size of a pulled image | §6.4 Table 7 |
| `update-delta --ssh H APP...` | bytes re-sent on a source-only bump | §5.3, §6.4 |
| `reproducibility --ssh H APP...` | byte-identical rebuild (`narHash`) | §6.2 R1, §6.4 |
| `report` | regenerates every paper figure from a run | §6.4 |

Examples:

```bash
H=hop3-dev.abilian.com
uv run hop3-bench memory          --ssh $H
uv run hop3-bench closures        --ssh $H miniflux vikunja mattermost gitea forgejo keycloak
uv run hop3-bench update-delta    --ssh $H miniflux gitea forgejo vikunja
uv run hop3-bench reproducibility --ssh $H miniflux
uv run hop3-bench cgroup-memory   --ssh $H hop3-server hop3-rootd    # framing A
```

`--nixpkgs-rev` defaults to `50ab793…` (nixos-24.11), the Hop3 nix-gen generator pin. Docker sizes need the image pulled first (`ssh root@$H docker pull -q <image>`).

## The matrix run

One command — `hop3-bench matrix` (`hop3_tooling/bench/matrix.py`) — blank-slates the box, installs Hop3, and measures every `(app, variant)` cell:

```bash
uv run hop3-bench matrix                      # all 4 variants, the full corpus
uv run hop3-bench matrix --variants nix,nix-gen
uv run hop3-bench matrix --skip-rebuild       # measure the box as-is (resume)
```

Three properties it enforces, each the fix for a way an earlier run went wrong:

- **It never creates a cloud box.** The bench owns exactly one dedicated server (`--server-id`, from `$HETZNER_SERVER_ID`), wiped by an *OS rebuild* — same server, same IP, fresh Ubuntu. A stray `hcloud server create` leaks paid infrastructure.
- **The corpus comes from the committed `protocol.yaml`**, not a list duplicated in the runner, so a run cannot drift from the pre-registration.
- **Each cell is flushed to the results file as it completes**, so an interrupted run keeps everything measured up to that point.

Results land in `notes/benchmarks/<date>-matrix.jsonl` (one JSON object per cell); full deploy logs are kept for failures only, since a success's timing *is* the measurement.

## Other orchestration (`scripts/`)

`deploy-timing.sh` (G1) and the baselines take an IP argument — get it with `hcloud server ip $HETZNER_SERVER_ID`.

```bash
IP=$(hcloud server ip $HETZNER_SERVER_ID)
notes/benchmarks/scripts/deploy-timing.sh $IP \
  apps/real-apps-native/miniflux apps/real-apps-nix-gen/forgejo apps/real-apps-docker/isso
```

K3s and Docker must never share a box: both mutate global netfilter/iptables state, so a co-resident run inherits the other's contamination. Rebuild between them (`hop3-bench matrix` does this for its own run; for baselines use `hcloud server rebuild $HETZNER_SERVER_ID --image ubuntu-24.04`).

## Metrics

| Metric | Definition | Tool |
|--------|-----------|------|
| Control-plane memory | PSS (RSS as cross-check) of `hop3-server` master + workers | `/proc/<pid>/smaps_rollup` |
| Cross-stack memory | systemd-service cgroup `memory.current` | `/sys/fs/cgroup/system.slice/<svc>.service/` |
| Nix closure | uncompressed sum of `narSize` over the runtime closure | `nix path-info -r --json` |
| Docker image | uncompressed image size | `docker image inspect .Size` |
| Dedup union | closure of several apps, each shared path counted once | `nix path-info -r` over all roots |
| Update delta | the app's own store-path `narSize` (deps pinned) | `nix path-info --json` |
| Reproducibility | byte-identical rebuild (`narHash` preserved) | `nix build --rebuild` |

Sizes are **uncompressed**, in MB (1 MB = 10⁶ bytes). `memory.current` charges page cache and counts only pages first faulted in by the cgroup, so it can fall either side of the resident set — never mix it with PSS/RSS in one comparison.

## Known limitations of the current run

- Every figure is **n=1** — no repeats, no confidence intervals.
- Reproducibility is checked on **one** application (Tier-1); Tier-2/Tier-3 are unmeasured.
- R2's "memory independent of app count" rests on **two points**, not a curve — apps are torn down after each `hop3-test` cycle, so the curve needs a persistent-deploy pass.
- Hop3's baseline figure was taken on the **dev host**, K3s/Compose on fresh boxes.
- Baselines cover K3s and Docker Compose; the closest peers (Dokku, Piku, CapRover, Coolify) are **not** measured.
- Per-app deploy timings include a cached re-provision check and teardown, so they **bound** deploy cost from above.

## Files

| File | What |
|------|------|
| `protocol.yaml` | pins (nixpkgs rev, corpus, hardware), metric definitions, per-benchmark status |
| `2026-07-19-preliminary.json` | the first run: memory, closure-vs-image, dedup, update delta, reproducibility, deploy timing, baselines |
| `scripts/` | deploy-timing + baseline orchestration (the matrix run is `hop3-bench matrix`) |
| `README.md` | this runbook |

Raw runs are the source of truth. Never hand-edit a number into the paper — measure it, then regenerate with `hop3-bench report`.
