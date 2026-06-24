# ADR 046: Declarative Application Resources — Generated Secrets, Persistent Volumes, Dynamic Env, and Resource Limits

- **Status**: Accepted
- **Type**: Feature
- **Created**: 2026-06-15
- **Authors**: Stefane Fermigier <sfermigier@gmail.com>
- **Related-ADRs**: 002 (hop3.toml format), 003 (config validation), 011 (encryption), 016 (backup strategy), 024 (backup/restore system), 035 (build artifacts), 040 (network/firewall/ports), 041 (privileged operations agent), 042 (CLI context model), 045 (fixed-port registry)

## Abstract

This ADR establishes a declarative model for application resources in `hop3.toml`: the app declares intent and the platform realizes it idempotently, failing loud when it cannot. It specifies five config surfaces — typed `[env]` values (generated secrets and dynamic references), `[[volumes]]` persistence, `[limits]` resource caps, resource-aware `[backup]` policy, and proxied secondary `[port]` endpoints — and consolidates deploy-time ignore patterns into `[build].ignore`. Realizations that cross the kernel privilege boundary (mounts, cgroups) run through the hop3-rootd agent (ADR 041) behind a single op contract.

## Context

Hop3's `hop3.toml` was modeled on Nua's `nua-config` (Hop3's predecessor). ADR 002 reserved a number of Nua-derived fields against future implementation, but several were never realized, and a side-by-side comparison of the two formats surfaced four capabilities that Nua expressed declaratively and Hop3 cannot. Each one forces a *per-app workaround* — which, by the project ethos, is a signal that the platform is missing something, not that the app is special.

The four gaps, each a real blocker hit while greening the advertised app/tutorial set:

1. **No generated secrets.** Many apps require a secret/key to exist *before first boot* (the release crashes without it). Hop3 has no way to declare "generate a secret named X once and keep it"; the only paths are hardcoding (forbidden) or out-of-band `hop3 config set` / `hop3 deploy --env X=$(...)`. This bites Phoenix (`SECRET_KEY_BASE`), Laravel (`APP_KEY`), and Rails (`secret_key_base`).
2. **No declarative persistence.** There is no `[[volumes]]`-equivalent. An app cannot declare which paths in its tree must survive the source-replacing redeploy, request a tmpfs, or attach a bind mount. The only persisted location is the implicit `data/` dir.
3. **No dynamic env references.** Hop3 auto-injects a *fixed, per-addon-type* env contract (`DATABASE_URL`, `PGHOST`, …). It cannot copy an arbitrary provider attribute, build a custom connection string from parts, reference a second instance, or read the host's public IP.
4. **No resource limits.** Nothing lets an app declare a memory or CPU cap. On a single box running many apps — Hop3's whole premise — one app can starve the others.

A correctness defect compounds the gap: the `[env]` `from`/`key`/`random` password-generation forms appear in examples but were never implemented — the loader (`Hop3Config.env`) drops dict-valued entries, so `SECRET = { generate = "hex" }` or `DB_HOST = { from = "database", key = "hostname" }` is **silently discarded**. A silent skip is exactly what the platform's non-negotiable rules forbid: the documented form promises a feature the runtime ignores.

This ADR is a single **umbrella** decision: it sets the direction and design principles for the whole declarative-resource surface, specifies the four capabilities above, **folds in and extends** two overlapping areas (backups → ADR 016/024; multi-port proxying → ADR 040), and defers the remainder (source-acquisition-by-config, descriptive metadata, addon version pinning) to *Future Work*.

## Motivation

The platform is about to advertise a curated set of apps as "working", where robustness is a core feature. Each of the four gaps otherwise ships as a bespoke workaround embedded in an app's deploy command or `hop3.toml` — the warning sign the ethos calls out:

- Generated secrets: framework tutorials carry a `hop3 deploy … --env KEY="$(…)"` workaround a fresh user must reproduce by hand, and that is not reproducible across redeploys.
- Persistence: stateful apps work "by accident" only as long as their data happens to land in `data/`; anything else is wiped by the redeploy's `git clean`.
- Dynamic env: apps whose connection string doesn't match the fixed injected names need manual `config set` glue.
- Limits: a single misbehaving app can OOM the box and take down every other tenant — a multi-tenant PaaS without per-app caps is not production-safe.

Left unaddressed, the advertised set stays fragile and order-dependent, the silent-drop defect keeps lying to users about their config, and the gap between the documented format (ADR 002) and the runtime widens.

## Decision

Adopt a **Hop3-native declarative model** that completes the config surface around one principle:

> **Declare intent in `hop3.toml`; the platform realizes it idempotently, and fails loud when it cannot.**

Tenets that bind the whole design:

- **Generated-once, never-rotate.** Generated secrets are created on first deploy when unset, persisted as normal app env, and never regenerated on redeploy. Redeploys stay idempotent; secrets never silently rotate and invalidate sessions/data.
- **Fail loud, never drop.** An unresolvable reference, an unknown `generate` type, an unsupported volume driver, or an unenforceable limit **aborts the deploy** with an actionable message. This removes the silent-drop of dict-valued env entries.
- **Hybrid env, not wholesale Nua.** Automatic fixed-name addon injection remains the ergonomic default (it covers the common case with zero config). Declarative secret generation and dynamic references *add* power for the cases injection cannot reach, rather than replacing injection with Nua's inline-dict model.
- **Functional core / imperative shell.** Env resolution is a pure transform `(config, addon facts, existing app env) → desired env`; the deployer applies the result. Volume linking and limit enforcement are the imperative shell, isolated at the deploy edge.
- **Additive and backwards compatible.** Every new form is opt-in; existing static `[env]` is unchanged. The one behavior change is a *fix*: dict-valued env entries are interpreted or rejected, never silently dropped.

Concretely, this ADR specifies:

1. `[env]` typed-value forms for **generated secrets** and **dynamic references**.
2. A `[[volumes]]` section for **declarative persistence**.
3. A `[limits]` section for **resource caps**.
4. Folded-in: `[backup]` **per-resource policy** extending ADR 024 (superseding the backup-config sketch in ADR 002 §backup); `[port]` **proxied secondary endpoints** extending ADR 040.
5. Consolidate **deploy ignore patterns** into `[build].ignore`, removing the `.hop3ignore` sidecar and the `[build].ignore-file` pointer.
6. Realize the privilege-crossing parts (kernel mounts, cgroups) through the hop3-rootd agent under one op contract (ADR 041).

It also closes the defect where the `from`/`key`/`random` `[env]` forms were documented in examples but never implemented; this model defines and interprets them as `generate` secrets and dynamic `from`/`key` references.

## Detailed Design

### 1. Env model — generated secrets + dynamic references

`[env]` values are a small discriminated union rather than "string, and dicts are dropped":

```
EnvValue = str | int | float | bool | EnvGenerate | EnvRef
```

A table value is dispatched by its keys: a `generate` key → `EnvGenerate`; a `from` or `external_ip` key → `EnvRef`. Any other table shape is a **validation error** (not a silent drop). `_policy` and the `[env.computed]` sub-table keep their existing special meaning.

#### 1a. Generated secrets — `EnvGenerate`

```toml
[env]
SECRET_KEY_BASE = { generate = "hex", length = 64 }
APP_KEY         = { generate = "base64", length = 32, prefix = "base64:" }
ADMIN_PASSWORD  = { generate = "password", length = 24, display = true }
SESSION_ID      = { generate = "uuid" }
```

- `generate` (required): one of `hex`, `base64`, `urlsafe`, `password`, `uuid`. Clearer than Nua's `random = true`; the type names the encoding so the app gets the shape it expects.
- `length` (optional): entropy in bytes for `hex`/`base64`/`urlsafe`, characters for `password`. Per-type default (e.g. 32 bytes).
- `prefix` (optional): literal string prepended after generation (Laravel needs `base64:`).
- `display` (optional, default `false`): surface the generated value **once** in deploy output, for bootstrap admin credentials. This is the only time a generated secret is shown.

**Semantics.** Generation uses the `secrets` module (CSPRNG — `token_hex`/`token_urlsafe`/`token_bytes`), never `random`. A value is generated only if the var is **unset**, then stored as a normal app `EnvVar` (encrypted at rest once ADR 011 lands) and **never regenerated**. This slots into the existing keep-existing/`_policy` model: a generated secret is a default that, once materialized, is preserved. Rotation is explicit: `hop3 config unset KEY && hop3 deploy` (a dedicated `hop3 config rotate` is Future Work).

This replaces the framework workarounds: Phoenix's `--env SECRET_KEY_BASE=$(mix phx.gen.secret)` becomes `SECRET_KEY_BASE = { generate = "hex", length = 64 }` in committed config, with no secret in the repo and reproducible first-boot.

#### 1b. Dynamic references — `EnvRef`

```toml
[env]
# Auto-injection still provides DATABASE_URL, PGHOST, … by default.
# Refs are for what injection can't express:
PRIMARY_DB_HOST = { from = "myapp-db", key = "PGHOST" }
APP_FQDN        = { key = "domain" }          # from the app itself
PUBLIC_IP       = { external_ip = true }
```

- `from` (optional): name of an addon attached to this app. Omitted = the app itself, for app facts such as `domain`. Resolution is app-scoped — it cannot read another app's credentials.
- `key`: the attribute to copy. With `from`, it is one of the addon's injected variable names (e.g. `PGHOST`, `DATABASE_URL`) — exactly what auto-injection already exposes, no more. Without `from`, it is an app fact: `domain` / `hostname` (the app's first hostname) or `name`. An unknown key fails the deploy and lists what is available.
- `external_ip = true`: the host's detected public IP, re-resolved each deploy (a host *fact*, never generated-once). Determination is sovereignty-first: an operator-set `HOP3_EXTERNAL_IP` / `_IP6`; else default-route detection (`ip route get` `src`, a kernel-local probe with no egress); else an opt-in `HOP3_EXTERNAL_IP_ECHO_URL` (https-only), off by default — the platform never phones home to learn its own address unless told to. A detected private/loopback/link-local address is **not** returned as public — it fails loud, because returning a private address as `PUBLIC_IP` is fake success. Auto-detection is therefore best-effort for bare-metal/non-NAT; cloud/NAT hosts must set `HOP3_EXTERNAL_IP`, and the error says exactly that. `family = "v4"|"v6"` selects.

Composition (Nua's f-string case) is handled by the **existing** `[env.computed]` `${VAR}` interpolation, the supported way to assemble a value from injected/referenced parts:

```toml
[env.computed]
CACHE_URL = "redis://${REDIS_HOST}:${REDIS_PORT}/1"
```

#### 1c. Resolution pipeline (pure function)

Applied in order; each step fails loud on an unresolvable ref / unknown addon / unknown key / unknown `generate` type:

1. Existing app env (config-set + previously-generated) — highest precedence under keep-existing.
2. Addon auto-injection (fixed-name vars).
3. Static `[env]` values (defaults).
4. `EnvGenerate` — only for vars still unset; result persisted.
5. `EnvRef` — resolved against addon facts + app facts (including `external_ip`).
6. `[env.computed]` `${VAR}` interpolation over the merged map.

The output is the desired env; the deployer reconciles it against the `EnvVar` store. `_policy = "override"` flips steps 2–4 to overwrite (generated secrets stay generated-once — override does not force rotation).

### 2. `[[volumes]]` — declarative persistence

```toml
[[volumes]]
name   = "uploads"          # logical name → storage id "<app>-uploads"
target = "data/uploads"     # path in the app tree (relative) or absolute
type   = "persist"          # persist (default) | tmpfs | bind

  [volumes.backup]          # optional; ties into ADR 024
  include = true
```

`realize_volumes` dispatches on `type`, aborting on an unknown type:

- **`persist`** (default): a directory under the app's data root (`/home/hop3/apps/<app>/volumes/<name>/`), linked into `target` on every deploy. It lives **outside `src/`**, so the redeploy sequence (stop-previous-instance → wipe & re-extract `src/` → `git clean`) cannot touch it; the link is re-established after extract, before start, which is the precise fix for "which tree paths survive a redeploy". An empty volume is seeded once from shipped content; the in-src link is relative; `mode` is honoured and the dir is chowned to the run-user on root deploys.
- **`tmpfs`**: a sized RAM mount at `src/<target>` (a real kernel mount, not a symlink), for caches/scratch. `size` is **required** and format-validated like `[limits].memory` — an uncapped tmpfs defaults to half of RAM, a multi-tenant footgun, so a sizeless tmpfs aborts at schema time; a cross-section validator rejects `Σ tmpfs size ≥ [limits].memory`. It is never seeded (scratch; shadowed shipped content is *logged*, not silently lost) and **never backed up** (a `[volumes.backup]` on a tmpfs is itself a config error).
- **`bind`**: an operator-approved host path, declared with a `source` field (absolute host path — the deliberate inverse of the relative `target`). Binding arbitrary host paths is a host-escape risk, so this is **default-deny**: only paths under an operator allow-list (`HOP3_BIND_VOLUME_ALLOWLIST`, empty by default) are accepted, with `source` `realpath`-resolved and re-checked against the resolved allow-list in *both* hop3-server and rootd (no symlink escape). Two apps binding the same source is the unmanaged-shared-resource hazard, so a `BindClaim` registry (mirroring `PortClaim`) detects contention and aborts. Backups **default-exclude** bind sources (operator-owned, possibly shared/huge); opt in with `[volumes.backup] include = true`. Destroy must never delete the source: the bytes live at `source` outside `app_path`, so once unmounted the mountpoint is an empty dir — but a *still-mounted* bind would make `rmtree(app_path)` follow into operator data, which the teardown gate below prevents.

**Realization by builder.** Native/Nix run on the host with cwd `src/`: `persist` is a relative symlink; `tmpfs`/`bind` are real kernel mounts made through hop3-rootd (§6). Docker bind-mounts the **same** host dir `<app>/volumes/<name>` into the container at `target`, so the host-side backup/restore path is byte-for-byte identical across builders; `tmpfs`/`bind` map to compose `tmpfs:`/`volumes:`. Docker seed-once copies the image's content at `target` into an empty host volume via a throwaway `docker create` + `docker cp` — a `docker cp` failure other than "path absent in image" aborts, so there is no silent empty volume. Per-volume `[volumes.backup]` makes ADR 024's backup/restore *resource-aware* (a volume is a backup unit).

**Teardown gate.** `App.stop()` (before `src/` is wiped) and `App.destroy()` (before any `rmtree`) must, for every declared native mount: reap processes, unmount (lazy `MNT_DETACH` fallback on EBUSY), then list mounts under the app and **raise if any survive** — refuse to delete over a live mount. Docker releases its own mounts when the container dies, and `compose down --volumes` never touches a host bind source.

### 3. `[limits]` — resource caps

```toml
[limits]
memory    = "512M"     # hard cap (OOM-killed above)
cpu       = 1.5        # cores, fractional
processes = 256        # max pids/threads (optional)
```

Enforcement is via the OS cgroup/process boundary, not the app runtime alone.

**Native (uWSGI) and Nix apps** run under a single Emperor (`uwsgi-hop3.service`) that runs every app's worker as an `attach-daemon` `exec` — a native app is *not* its own systemd unit. The enforcement surface is therefore a **per-app cgroup v2 leaf** (`hop3.slice/hop3-app-<name>.scope`) that rootd (§6) creates and into which the app's PIDs are migrated, independent of who spawned them. Mapping: `memory → memory.max` (plus `memory.swap.max = 0`, so a cap is a real cap, not spill-to-swap), `cpu → cpu.max` (`round(cpu*100000) 100000`), `processes → pids.max`. cgroup v2 only; v1/hybrid hosts fail loud.

**Docker apps** map to `--memory`, `--cpus`, `--pids-limit`, with swap-off set for parity so OOM timing matches the native path.

**Keeping respawns capped.** Caps are applied post-start, because an app's PIDs exist only once it is RUNNING: rootd ensures the leaf, writes the caps, then attaches the live PIDs. With the leaf as the entry gate, worker respawns the Emperor forks from an already-attached master inherit the cap by cgroup v2 inheritance. The rarer whole-vassal respawn (a fresh master) and a rootd restart (whose reconcile re-creates the leaf + caps but not PID membership) are covered by a periodic re-attach over **all RUNNING** native-capped apps — not just transitional ones — so there is no silent uncapped window; the re-attach surfaces, rather than swallows, any failure. The leaf persists across a redeploy's stop → rebuild → start.

**Server-wide default + ceiling.** Two operator settings on `HopConfig`, both off by default (single-tenant boxes and the test suite are unaffected): a per-dimension **default** applied where an app declares nothing, and a per-dimension **ceiling** (the multi-tenant safety net). Resolution is a pure `resolve_limits(declared, defaults, ceilings)` transform feeding both the cgroup ops and the Docker mapping, so defaults/ceilings apply uniformly across builders. A declared value above the ceiling **aborts** — never silently clamps down, because silently giving an app less than it asked for is the same class of lie as not enforcing.

**Fail-loud rule and modes.** A declared limit is a safety guarantee. In strict mode (default), any unenforceable declared/defaulted limit **aborts the deploy**, and an already-started app is stopped rather than left running uncapped — the guarantee is "capped or not running", never an app that only looks limited. An operator may opt into a best-effort mode: the app runs, but the unenforced state is recorded on the App row (`limits_enforced` / `limits_detail`) and shown by `hop3 app status` / `debug`, so the failure is surfaced where the user looks. A declared value over the ceiling aborts in **both** modes (a config error, not an enforcement gap). OOM kills are surfaced via `memory.events::oom_kill` in status.

**Teardown.** `destroy` removes the cgroup leaf for every runtime (so a native→Docker redeploy leaves no orphan leaf), and `cgroup.kill` is a stronger reap surface than `/proc` scanning for the Nix-store `exec` heisenbug.

### 4. Folded-in extensions

#### 4a. Backups — extend ADR 024, supersede ADR 002 §backup

`[backup]` is a resource-aware policy, reconciling the doc/schema mismatch (the docs describe `enabled`/`schedule`/`retention`; the schema previously allowed only `paths`/`exclude` under `extra="forbid"`, so the documented example failed validation):

```toml
[backup]
schedule  = "0 2 * * *"     # cron
retention = 7               # days
paths     = ["data"]
exclude   = ["*.tmp"]

[[addons]]
type = "postgres"
  [addons.backup]
  method   = "pg_dump"
  schedule = "0 3 * * *"
```

Plus per-`[[volumes]]` `[volumes.backup]`. This is the config-surface layer over the backup *system* of ADR 024 (extended, not replaced), superseding the backup-config sketch in ADR 002.

**Schema.** `enabled` + `schedule` (5-field cron, UTC; required when `enabled`) + `[backup.retention]` (`days` / `keep-last`) + the wired `paths`/`exclude`, plus a strict `[addons.backup]` (`method`/`schedule`/`retention`). All `extra="forbid"`, all fail-loud at schema time. The cron matcher is stdlib-only (no `croniter`).

**Scheduler.** An in-process background service in the ASGI lifespan, structurally identical to the cert-renewal / state-sync / domain-health services (a daemon thread + stop-event + a testable `run_once()`), polling each minute. It needs no rootd and no new dependency, and — crucially — leaves **no per-app host artifact**: a systemd timer or `/etc/cron.d` entry would survive `destroy` (a leftover, hence a platform bug). "Did the cron minute elapse" is computed from the existing `Backup` rows, so there is no separate scheduling table.

**Failure visibility.** The authoritative state of a backup is its `Backup` row, not a manifest: a FAILED backup writes no manifest and its partial dir is removed. The read path therefore reads `state` plus an `error` column from the rows and merges manifest detail only for COMPLETED rows — without this, a failed scheduled backup would be fire-and-forget. The scheduler catches per-app (one failure doesn't stop the cycle) but logs loudly, leaves the row FAILED with its `error`, and refuses to start a second backup while one is in progress for the app (no overlap). A `scheduled` provenance flag distinguishes manual from scheduled backups, and an "overdue" indicator (newest scheduled COMPLETED vs the cron) surfaces a scheduler that has silently stopped.

**Retention** runs in the same cycle: it prunes only `scheduled, COMPLETED` backups by `days` and/or `keep-last` (the more conservative when both are set), removing directory and row together, and **always excludes the single most recent good backup** — logging when it keeps one against policy, never silently leaving zero.

**`paths`/`exclude`** compose into the existing tar filter (the volume-link drop keeps precedence); `paths` is archived separately so restore doesn't lose it to the redeploy's `git clean`. A declared-but-missing `paths` entry **aborts** the backup (no silent omission). Per-addon `method` validates against a `supported_backup_methods` capability on the addon protocol (fix-the-class, not per-type knowledge in the manager). On teardown, `destroy` removes the app's backup directory tree (the FK cascade drops rows; the directories would otherwise be a disk leftover).

#### 4b. Proxied secondary endpoints — extend ADR 040

Hop3 routes HTTP by hostname on a dynamic `$PORT`; raw non-HTTP ports use `[[ports]]` (ADR 040/045). The missing case is a *second proxied HTTP(S) endpoint* (e.g. an admin UI on a different container port):

```toml
[port.web]
container = "$PORT"          # default: proxied on 443 by the app's hostnames

[port.admin]
container = 9090
proxy     = true            # nginx proxies this endpoint
subdomain = "admin"         # served at admin.<host>; inherits TLS
```

`PortConfig` gains `proxy`/`subdomain`/`path` while keeping its `container`/`public`/`https` fields (additive, no break): a named endpoint with `proxy = true` requires exactly one of `subdomain` (served at `<sub>.<host>`) or `path` (served at `<host><path>`, rendered ahead of `location /`). nginx renders the endpoint into the **same** `<app>.conf` (one atomic teardown unit) as an extra `server{}` (subdomain) or `location{}` (path). The container port is reached on loopback — native: the app binds `127.0.0.1:<container>`; Docker: publish `127.0.0.1:<hostport>:<container>` — and a post-start probe **asserts the port answers on loopback and is refused on a non-loopback address**, so a publicly-bound secondary listener (bypassing nginx/TLS) aborts the deploy rather than silently exposing an admin UI. Raw, non-HTTP ports stay in `[[ports]]`; no app binds 80/443 directly — the proxy multiplexes.

**TLS.** A `subdomain` adds a hostname the served cert must cover, so issuance is **multi-SAN** (the self-signed engine accepts a name list; certbot adds `-d` per name), and cert verification runs over **every** secondary FQDN so a missing SAN fails loud rather than serving a mismatch. Teardown is complete by construction (same conf file, same cert pair); Docker verifies the published loopback port is released so it can't block the next deploy's port allocation. A `subdomain` endpoint depends on multi-SAN issuance; a `path` endpoint shares the primary cert and has no such dependency.

### 5. Deploy ignore patterns — `[build].ignore`, not `.hop3ignore`

Deploy-time ignore patterns (what *not* to bundle and upload) are configuration about the app, so by the same tenet — *declare intent in `hop3.toml`, not a sidecar* — they belong in `hop3.toml`, not a Hop3-invented dotfile. (Before this decision the surface was split: the CLI bundler read a `.hop3ignore` sidecar, while the schema declared an unwired `[build].ignore` / `[build].ignore-file`, the latter a field whose value is "go read this other file".)

- **`[build].ignore`** (an inline glob list) is the single canonical, method-agnostic way to declare what is *not* part of the app, and is the mechanism for the `hop3 deploy` upload path (where the CLI tars the working tree):

  ```toml
  [build]
  ignore = ["*.log", "node_modules/", "tmp/", ".env"]
  ```

- **A built-in default ignore set always applies** (and `[build].ignore` extends it): VCS metadata and dependency/cache dirs the server regenerates — `.git/`, `node_modules/`, `.venv/`, `venv/`, `__pycache__/`, `*.py[cod]`, `.idea/`, `.DS_Store`, `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, `*.egg-info/`. This is what makes the `.gitignore` upload-fallback unnecessary: the common junk is excluded with zero config, so most apps need no `ignore` at all.

- **`.hop3ignore` and `[build].ignore-file` are removed** — the sidecar and the pointer that re-introduces a sidecar.

- **Standard ecosystem ignore files apply only in their native context**, never for the generic `hop3 deploy` upload:
  - **`.gitignore` → git-push only.** With a `git push` deploy the transport *is* git, so `.gitignore` already governs what reaches the server; Hop3 does nothing special and does not consult it for the upload.
  - **`.dockerignore` → the `docker` builder.** Docker filters its build context by `.dockerignore`, the standard file it already honors; Hop3 leaves that to Docker.

  These are real, ecosystem-standard files tied to a specific transport/builder, so honoring them in their own context surprises no one. The generic-upload role belongs to `[build].ignore`.

### 6. Privileged realization via hop3-rootd (extends ADR 041)

Native `tmpfs`/`bind` mounts (§2) and native `[limits]` (§3) require privileged kernel operations outside rootd's `firewall.*` / `nginx.*` / `daemon.*` families. Rather than two drifting extensions, both are introduced as **one** amendment behind a single client/state/validation contract:

- **`mount.*`** — `mount.tmpfs`, `mount.bind`, `mount.unmount`, `mount.list`.
- **`cgroup.*`** — `cgroup.ensure_slice`, `cgroup.set_limits`, `cgroup.attach_pids`, `cgroup.remove` (kills the subtree, then rmdir), `cgroup.read`.

What makes it one amendment rather than two:

- **One path-allow-list.** rootd re-derives `APP_ROOT` and runs `validate_app_name` for both families; every `mountpoint`/leaf must canonicalize under `<APP_ROOT>/<app>/src/` resp. `hop3.slice/hop3-app-<app>.scope`. Callers never pass arbitrary paths.
- **One state file + reconcile loop.** Mounts and cgroup leaves join the firewall family's atomic-write/reconcile discipline, so a rootd restart re-asserts or cleans exactly what it owns.
- **One threat model.** The op families run within rootd's existing root privilege. The larger trust budget the union implies — `CAP_SYS_ADMIN` (mounts), a non-private mount namespace (so an Emperor-spawned process can see a rootd-made mount), and `ProtectControlGroups=false` or a delegated `hop3.slice` — is a forward constraint for the unit-hardening pass, threat-modelled as a whole rather than loosened ad hoc.

A realization that requires a privileged op is gated on that op: the platform refuses a resource it cannot realize rather than deploy something that only looks capped or persisted. If the amendment were rejected, native tmpfs/bind and native limits would be infeasible and only the Docker paths would be available — the guaranteed-deployable baseline.

## Examples

**Phoenix — generated secret replaces the deploy-time workaround:**

```toml
[metadata]
id = "hop3-tuto-phoenix"

[build]
builder = "nix"

[env]
SECRET_KEY_BASE = { generate = "hex", length = 64 }

[[addons]]
type = "postgres"
```

`hop3 deploy` — no `--env`, no secret in the repo, reproducible.

**Stateful app — persistence + per-resource backup + limits:**

```toml
[metadata]
id = "notes"

[[volumes]]
name = "uploads"
target = "data/uploads"
  [volumes.backup]
  include = true

[limits]
memory = "768M"
cpu = 1.0

[[addons]]
type = "postgres"
  [addons.backup]
  method = "pg_dump"
  schedule = "0 3 * * *"
```

`[limits]` applies on both builders; `persist` volumes realize on every builder via the shared host dir, while `tmpfs`/`bind` volumes are host mounts realized on the native/Nix builders.

## Consequences

### Positive

- Closes the four gaps; removes the per-app workarounds the ethos warns against.
- Fixes the silent-drop defect — config is honored or rejected, never quietly ignored.
- Generated-once secrets make first-boot reproducible and redeploys idempotent.
- Declarative persistence makes stateful apps survive redeploys by design, where they previously survived only when their data happened to land in `data/`.
- Per-app limits make the multi-tenant single box production-safe.
- Aligns the documented format (ADR 002) with the runtime, and the docs with the schema.

### Negative

- Schema complexity: `[env]` gains a discriminated union; new sections to validate and test.
- New realization paths (volume linking, cgroup wiring) with OS variance, several depending on hop3-rootd (ADR 041) — a hard dependency for limits and bind/privileged mounts.
- A behavior change at the edge: dict-valued env entries previously ignored are now interpreted or rejected; a few existing configs may surface previously-dead entries (see Backwards Compatibility).
- Touches several existing ADRs (002 corrected, 016/024 extended, 040 extended).

## Security Implications

- **Secrets**: CSPRNG only (`secrets`); stored encrypted at rest once ADR 011 lands; never logged except a `display = true` one-shot to deploy output (documented, opt-in).
- **`bind` volumes**: host-path escape risk → default-deny with an operator allow-list, `realpath`-checked in both server and rootd.
- **Dynamic refs**: resolve only against each addon's documented key contract; no new exposure beyond auto-injection.
- **`external_ip`**: exposes the host's own public IP to its own app — acceptable; a private address is never returned as public.
- **Resource limits**: a DoS mitigation. A declared-but-unenforced limit is a false guarantee → abort by default.
- **Proxied secondary endpoints**: a loopback-only invariant (probed at deploy) keeps a secondary listener from bypassing nginx/TLS; subdomains are covered by the served cert (multi-SAN) or the deploy fails loud.

## Backwards Compatibility

- Additive: static `[env]`, existing `[[addons]]`, `[run]`, etc. are unchanged.
- The one change: dict-valued `[env]` entries previously dropped are now interpreted (known forms) or rejected at validation (unknown shapes). This is a fix; the migration note calls it out and validation flags affected files.
- The `from`/`key`/`random` `[env]` forms — documented but never implemented — are now defined and interpreted. ADR 016 and 024 extended for resource-aware backup policy; ADR 040 extended for proxied secondary endpoints. No deployed app breaks.
- `.hop3ignore` is replaced by `[build].ignore`, and `[build].ignore-file` is removed. A present `.hop3ignore` is honoured for one release with a loud deprecation warning that points to `[build].ignore`, then dropped (no silent shim). The CLI's `.gitignore` fallback for the upload is removed — `.gitignore` belongs to the git-push path. git-push users (relying on `.gitignore`) and Docker users (relying on `.dockerignore`) are unaffected.

## Alternatives Considered

- **Adopt Nua's inline-dict env model wholesale** (`{from, key, random}` as the primary mechanism, injection opt-in). Rejected: auto-injection is more ergonomic for the overwhelmingly common single-database case; the hybrid keeps that and adds power only where needed.
- **Secrets only via `hop3 config set`.** Rejected: cannot run before the first deploy, which is exactly when boot-crashing releases (Phoenix) need the value; not reproducible from the repo.
- **Regenerate secrets every deploy.** Rejected: non-idempotent; rotates sessions/keys and corrupts data on every redeploy.
- **Resource limits via uWSGI knobs only.** Rejected: incomplete and runtime-specific; the cgroup boundary is the real enforcement surface and covers Docker/Nix too.
- **No volumes; rely on the implicit `data/`.** Rejected: apps cannot declare which tree paths persist, forcing bespoke layout hacks.
- **Per-app systemd units / timers for limits and scheduled backups.** Rejected: a unit or timer survives `destroy` as a host leftover; a per-app cgroup leaf and an in-process scheduler leave no artifact.

## Prior Art

- **Nua `nua-config`**: `[[volume]]` (managed/directory/tmpfs/remote), `{from/key/random/external_ip}` env, `[docker].mem_limit`, per-resource backup.
- **Heroku**: config vars; no persistence (Hop3 goes further with volumes).
- **Docker Compose**: `volumes`, `mem_limit`/`cpus`, per-service config.
- **Kubernetes**: Secrets, PersistentVolumeClaims, resource requests/limits — the conceptual model for declare-and-reconcile.
- **systemd resource control**: `MemoryMax`, `CPUQuota`, `TasksMax` — the conceptual native enforcement mechanism (realized here as a cgroup v2 leaf, since native apps are not their own units).

## Unresolved Questions

- Secret rotation UX (`hop3 config rotate KEY`?).
- Per-context (ADR 042) overrides for volumes / limits / generated secrets — likely desirable.
- cgroup enforcement on non-systemd hosts: native limits write `hop3.slice` directly via rootd (no systemd delegation), which is the open feasibility risk where rootd runs under a supervisor rather than systemd; `tmpfs`/`bind` inherit it.
- The recommended server-wide default limit for a multi-tenant box, and whether to enable it by default once mature.
- The per-endpoint healthcheck shape for proxied secondary endpoints, and a `$PORT`-style dynamic secondary port.

## Future Work

- **Source-acquisition-by-config**: generalize the Nix `url` + `sha256` story to `[build]` `src-url` + `src-checksum`, `git-url`/`git-branch`, and `base-image` + `method = "wrap"`.
- **Descriptive metadata**: `tagline`, `release`, `profile` (low priority).
- **Addon version pinning** and a `mongodb` addon type.
- `hop3 config rotate` for secret rotation.

## References

- ADRs 002, 003, 011, 016, 024, 035, 040, 041, 042, 045.
- Nua specs: `sandbox/nua/doc/src/dev/specifications/{nua-config,configuration}.md`.
- Python `secrets`; systemd resource control; Docker resource constraints.
