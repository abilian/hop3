# ADR 046: Declarative Application Resources — Generated Secrets, Persistent Volumes, Dynamic Env, and Resource Limits

**Status**: Accepted
**Type**: Feature
**Created**: 2026-06-15
**Authors**: Stefane Fermigier <sfermigier@gmail.com>
**Related-ADRs**: 002 (hop3.toml format), 003 (config validation), 011 (encryption), 016 (backup strategy), 024 (backup/restore system), 035 (build artifacts), 040 (network/firewall/ports), 041 (privileged operations agent), 042 (CLI context model), 045 (fixed-port registry)

## Implementation Status

Phase 1 is landing incrementally. Shipped so far:

- **Generated secrets** (`[env] { generate = ... }`) — `hex`/`base64`/`urlsafe`/`password`/`uuid`, generated-once with a CSPRNG, persisted as normal app env, validated at schema time, wired into the deploy pipeline between static `[env]` and `[env.computed]`. Replaces the `hop3 deploy --env KEY=$(...)` workaround. See `deployers/env_provisioning.py::generate_secret_value` / `set_generated_env_vars`, `project/schema.py::EnvGenerate`, `docs/src/reference/config.md` §"Generated secrets".
- **Ignore consolidation (§5)** — the `hop3 deploy` upload now excludes a built-in default set plus `[build].ignore`; `.gitignore` is no longer consulted for the upload (git-push only), `.dockerignore` stays a Docker-build concern, `.hop3ignore` is honored for one release with a loud deprecation warning, and `[build].ignore-file` is removed (schema rejects it). See `hop3-cli/commands/arguments.py::get_ignored_spec`, `project/schema.py::BuildSection`, `docs/src/reference/config.md` §"Excluding files from the upload".
- **Dynamic env references (§1b)** — `{ from = "<addon>", key = "<KEY>" }` copies an attribute from one of the app's addons; `{ key = "domain"/"hostname"/"name" }` reads an app fact. Resolved at step 5 (after the domains→HOST_NAME step, before `[env.computed]`), overwriting like computed; fails loud on an unattached addon / unknown key / unknown fact. The schema validator is now the single classifier for `[env]` table values and rejects unrecognised shapes (the ADR's fail-loud, previously unenforced). `external_ip` is recognised but not implemented — it raises a clear deploy error. See `project/schema.py::EnvRef`, `deployers/env_provisioning.py::resolve_env_refs`, `docs/src/reference/config.md` §"Dynamic references".
- **Persistent volumes (§2), `persist` type** — `[[volumes]]` links a directory in the app tree to storage under `<app>/volumes/<name>/` (outside `src/`), realized after extract and before the prebuild hook, so it survives the redeploy that wipes `src/`. Seeds an empty volume once from shipped content; idempotent on redeploy; honours `mode` and chowns to the run-user on root deploys; the in-src link is relative. `tmpfs`/`bind` are recognised but raise a clear "not implemented" deploy error (they need privileged mounts via rootd). See `project/schema.py::VolumeSection`, `deployers/volumes.py::realize_volumes`, `docs/src/reference/config.md` §"Persistent Volumes". Proven by `apps/test-apps-procfile/170-flask-volume`.
- **Volumes integrate safely with the rest of the platform** (audit follow-up): backups archive each volume as its own unit and restore round-trips them (no more silent exclusion / `AbsoluteLinkError`-on-restore); per-volume `[volumes.backup] include = false` opts out; `hop3 app destroy` removes data/volumes as a complete teardown but warns loudly first (its dead "preserve data" branch is gone); and `[[volumes]]` under the Docker builder aborts loudly (the container can't see a host symlink). See `core/backup.py`, `orm/app.py::destroy`, `deployers/deployer.py::_reject_volumes_on_docker`.
- **Resource limits (§3), Docker builder** — `[limits]` (`memory` / `cpu` / `processes`) is enforced for Docker apps via compose `mem_limit` / `cpus` / `pids_limit`. A declared limit is a safety guarantee, so `[limits]` on a non-Docker app **aborts the deploy** (native/Nix cgroup enforcement needs hop3-rootd and isn't built yet) — never silently un-enforced. See `project/schema.py::LimitsSection`, `plugins/docker/deployer.py::_compose_limits_section`, `deployers/deployer.py::_reject_limits_on_non_docker`, `docs/src/reference/config.md` §"Resource Caps".

Not yet implemented, but each **designed in [Phase 2 Design](#phase-2-design--deferred-features) below**: `external_ip` references, `tmpfs`/`bind` volumes, `[[volumes]]` for the Docker builder, native/Nix `[limits]` enforcement (cgroups via rootd), the server-wide default + ceiling `[limits]`, the best-effort opt-in limit mode, scheduled/retained backups (`[backup].paths`/`exclude` are reserved-but-inert today), per-addon backup policy, and the folded-in multi-port extension. Phase 2 also specifies the single hop3-rootd amendment (ADR 041) the privileged items share, and the order they ship in.

## Context

Hop3's `hop3.toml` was modeled on Nua's `nua-config` (Hop3's predecessor). ADR 002 reserved a number of Nua-derived fields against future implementation, but several never shipped, and a side-by-side comparison of the two formats (`local-notes/nua-vs-hop3-config-comparison.md`) surfaced four capabilities that Nua expressed declaratively and Hop3 cannot. Each one currently forces a *per-app workaround* — which, by the project ethos, is a signal that the platform is missing something, not that the app is special.

The four gaps, each one a real blocker we have hit while greening the advertised app/tutorial set:

1. **No generated secrets.** Many apps require a secret/key to exist *before first boot* (the release crashes without it). Hop3 has no way to declare "generate a secret named X once and keep it"; the only paths are hardcoding (forbidden) or out-of-band `hop3 config set` / `hop3 deploy --env X=$(...)`. We hit this with Phoenix (`SECRET_KEY_BASE`), Laravel (`APP_KEY`), and Rails (`secret_key_base`).
2. **No declarative persistence.** There is no `[[volumes]]`-equivalent. An app cannot declare which paths in its tree must survive the source-replacing redeploy, request a tmpfs, or attach a bind mount. The only persisted location is the implicit `data/` dir.
3. **No dynamic env references.** Hop3 auto-injects a *fixed, per-addon-type* env contract (`DATABASE_URL`, `PGHOST`, …). It cannot copy an arbitrary provider attribute, build a custom connection string from parts, reference a second instance, or read the host's public IP.
4. **No resource limits.** Nothing lets an app declare a memory or CPU cap. On a single box running many apps — Hop3's whole premise — one app can starve the others.

**A correctness finding that motivates acting now:** ADR 002's "Implementation Status" lists `[env]` `from`/`key`/`random` password generation as *shipped*. They are **not implemented**. The live loader (`project/hop3_config.py::Hop3Config.env`) explicitly drops dict-valued entries (`not isinstance(v, dict)`), and no `random`/`from`/`key`/`external_ip` handling exists in the deployer. So today `SECRET = { generate = true }` or `DB_HOST = { from = "database", key = "hostname" }` is **silently discarded** — a silent-skip, which the platform's own non-negotiable rules forbid. The format promises a feature the runtime ignores.

Per the answer to the scoping question, this ADR is a single **umbrella** decision: it sets the direction and design principles for the whole declarative-resource surface, fully specifies the four Phase-1 capabilities above, **folds in and extends** the two overlapping areas (backups → ADR 016/024; multi-port proxying → ADR 040), and defers the remainder (source-acquisition-by-config, descriptive metadata, addon version pinning) to *Future Work*.

## Motivation

**Why now.** We are about to advertise a curated set of apps as "working." Robustness is a feature, not a nice-to-have. Every one of the four gaps currently ships as a bespoke workaround embedded in an app's deploy command or `hop3.toml`, which is exactly the warning sign the ethos calls out. Concretely:

- Generated secrets: three framework tutorials already carry a `hop3 deploy … --env KEY="$(…)"` workaround that a fresh user copying the docs must reproduce by hand, and that is not reproducible across redeploys.
- Persistence: stateful apps work "by accident" only as long as their data happens to land in `data/`; anything else is wiped by the redeploy's `git clean`.
- Dynamic env: apps whose connection string doesn't match our fixed injected names need manual `config set` glue.
- Limits: a single misbehaving app can OOM the box and take down every other tenant — a multi-tenant PaaS without per-app caps is not production-safe.

**If we do nothing.** The advertised set stays fragile and order-dependent, the silent-drop bug keeps lying to users about their config, and the gap between the documented format (ADR 002) and the runtime widens.

## Decision

Adopt a **Hop3-native declarative model** that completes the config surface around one principle:

> **Declare intent in `hop3.toml`; the platform realizes it idempotently, and fails loud when it cannot.**

Tenets that bind the whole design:

- **Generated-once, never-rotate.** Generated secrets are created on first deploy when unset, persisted as normal app env, and never regenerated on redeploy. Redeploys stay idempotent; secrets never silently rotate and invalidate sessions/data.
- **Fail loud, never drop.** An unresolvable reference, an unknown `generate` type, an unsupported volume driver, or an unenforceable limit **aborts the deploy** with an actionable message. This directly removes the current silent-drop of dict-valued env entries.
- **Hybrid env, not wholesale Nua.** Keep automatic fixed-name addon injection as the ergonomic default (it covers the common case with zero config). *Add* declarative secret generation and dynamic references for the cases injection cannot reach. (This was the chosen direction over resurrecting Nua's inline-dict model as the primary mechanism.)
- **Functional core / imperative shell.** Env resolution is a pure transform `(config, addon facts, existing app env) → desired env`; the deployer applies the result. Volume linking and limit enforcement are the imperative shell, isolated at the deploy edge.
- **Additive and backwards compatible.** Every new form is opt-in; existing static `[env]` is unchanged. The one behavior change is a *fix*: dict-valued env entries are now interpreted or rejected, never silently dropped.

Concretely, this ADR specifies:

1. `[env]` typed-value forms for **generated secrets** and **dynamic references** (Phase 1).
2. A new `[[volumes]]` section for **declarative persistence** (Phase 1).
3. A new `[limits]` section for **resource caps** (Phase 1).
4. Folded-in: `[backup]` **per-resource policy** extending ADR 024 (and superseding the backup-config sketch in ADR 002 §backup); `[port]` **proxied secondary endpoints** extending ADR 040.
5. Consolidate **deploy ignore patterns** into `[build].ignore`, removing the `.hop3ignore` sidecar and the `[build].ignore-file` pointer; ecosystem-standard ignore files apply only in their native context (`.gitignore` → git-push, `.dockerignore` → docker), never for the generic `hop3 deploy` upload.

It also corrects ADR 002: `from`/`key`/`random` move from "shipped" to "specified here, not yet implemented."

## Detailed Design

### 1. Env model — generated secrets + dynamic references

`[env]` values become a small discriminated union instead of "string, and dicts are dropped":

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
- `display` (optional, default `false`): surface the generated value **once** in deploy output, for bootstrap admin credentials. Documented as the only time a generated secret is shown.

**Semantics.** Generation uses the `secrets` module (CSPRNG — `token_hex`/`token_urlsafe`/`token_bytes`), never `random`. A value is generated only if the var is currently **unset**, then stored as a normal app `EnvVar` (encrypted at rest once ADR 011 lands) and **never regenerated**. This slots cleanly into the existing keep-existing/`_policy` model: a generated secret is a default that, once materialized, is preserved. Rotation is explicit: `hop3 config unset KEY && hop3 deploy` (a dedicated `hop3 config rotate` is Future Work).

This replaces all three framework workarounds: Phoenix's `--env SECRET_KEY_BASE=$(mix phx.gen.secret)` becomes `SECRET_KEY_BASE = { generate = "hex", length = 64 }` in committed config, with no secret in the repo and reproducible first-boot.

#### 1b. Dynamic references — `EnvRef`

```toml
[env]
# Auto-injection still provides DATABASE_URL, PGHOST, … by default.
# Refs are for what injection can't express:
PRIMARY_DB_HOST = { from = "myapp-db", key = "PGHOST" }
APP_FQDN        = { key = "domain" }          # from the app itself
PUBLIC_IP       = { external_ip = true }      # not implemented yet
```

- `from` (optional): name of an addon attached to this app. Omitted = the app itself, for app facts such as `domain`. Resolution is app-scoped — it cannot read another app's credentials.
- `key`: the attribute to copy. With `from`, it is one of the addon's injected variable names (e.g. `PGHOST`, `DATABASE_URL`) — i.e. exactly what auto-injection already exposes, no more. Without `from`, it is an app fact: `domain` / `hostname` (the app's first hostname) or `name`. An unknown key fails the deploy and lists what is available.
- `external_ip = true`: the host's detected public IP — recognised but **not implemented yet** (raises a clear deploy error; use `hop3 config set` meanwhile). Designed in **Phase 2 (P2.4)**.

Composition (Nua's f-string case) is handled by the **existing** `[env.computed]` `${VAR}` interpolation, which we keep and document as the supported way to assemble a value from injected/referenced parts:

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
5. `EnvRef` — resolved against addon facts + app facts.
6. `[env.computed]` `${VAR}` interpolation over the merged map.

The output is the desired env; the deployer reconciles it against the `EnvVar` store. `_policy = "override"` flips steps 2–4 to overwrite (generated secrets are still generated-once — override does not force rotation).

### 2. `[[volumes]]` — declarative persistence

```toml
[[volumes]]
name   = "uploads"          # logical name → storage id "<app>-uploads"
target = "data/uploads"     # path in the app tree (relative) or absolute
type   = "persist"          # persist (default) | tmpfs | bind

  [volumes.backup]          # optional; ties into ADR 024
  include = true
```

- `type = "persist"` (default): a directory under the app's data root (`/home/hop3/apps/<app>/volumes/<name>/`), linked into `target` on every deploy. **It lives outside `src/`**, so the redeploy sequence (stop-previous-instance → wipe & re-extract `src/` → `git clean`) cannot touch it; the link is re-established after extract, before start. This is the precise fix for "which tree paths survive a redeploy".
- `type = "tmpfs"`: a RAM-backed dir (`size`, `mode` options) for caches/scratch.
- `type = "bind"`: an operator-approved host path. Binding arbitrary host paths is a host-escape risk, so this is **default-deny**: only paths under an operator-configured allow-list are accepted; anything else aborts the deploy.

Realization by builder: native/Nix → bind-mount or symlink into the app tree via the deploy shell (privileged mounts through hop3-rootd, ADR 041); Docker → container volume/mount. Per-volume `[volumes.backup]` makes ADR 024's backup/restore *resource-aware* (a volume becomes a backup unit).

Phase 1 ships `persist` only; `tmpfs`, `bind`, and `[[volumes]]` on the Docker builder are fully designed in **Phase 2 (P2.1)**.

### 3. `[limits]` — resource caps

```toml
[limits]
memory    = "512M"     # hard cap (OOM-killed above)
cpu       = 1.5        # cores, fractional
processes = 256        # max pids/threads (optional)
```

Enforcement is via the OS cgroup/process boundary, applied by hop3-rootd (ADR 041), not by the app runtime alone:

- Native (uWSGI) and Nix apps: a per-app systemd slice / cgroup (`MemoryMax`, `CPUQuota`, `TasksMax`).
- Docker apps: `--memory`, `--cpus`, `--pids-limit`.

**Fail-loud rule.** A *declared* limit is a safety guarantee. If the platform cannot enforce it (rootd unavailable, cgroup controller missing), the deploy **aborts** — it must never start an app that looks limited but isn't (no fake success). An operator may opt into a documented best-effort mode, which then **logs loudly and records** the unenforced state where the user looks. *(Deferred — not yet implemented; see Implementation Status.)*

A server-wide **default limit** (operator-configurable) protects multi-tenant boxes even when an app declares nothing. *(Deferred — depends on the same rootd cgroup support as native enforcement; see Implementation Status.)*

Phase 1 enforces `[limits]` on the Docker builder only; native/Nix cgroup enforcement, the server-wide default + ceiling, and the best-effort mode are fully designed in **Phase 2 (P2.2)**.

### 4. Folded-in extensions

#### 4a. Backups — extend ADR 024, supersede ADR 002 §backup

Reconcile the current doc/schema mismatch (`docs/src/reference/config.md` documents `enabled`/`schedule`/`retention`; the schema only allows `paths`/`exclude` and is `extra="forbid"`, so the documented example fails validation) by promoting `[backup]` to a real, resource-aware policy:

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

Plus per-`[[volumes]]` `[volumes.backup]`. This is the config-surface layer over the backup *system* already specified by ADR 024 (which is extended, not replaced); it supersedes the backup-config sketch in ADR 002.

Scheduling, retention, the wiring of `paths`/`exclude`, and per-addon policy are fully designed in **Phase 2 (P2.3)** — including the in-process scheduler choice and the read-path change that makes a *failed* scheduled backup visible.

#### 4b. Proxied secondary endpoints — extend ADR 040

Hop3 routes HTTP by hostname on a dynamic `$PORT`; raw non-HTTP ports use `[[ports]]` (ADR 040/045). The missing case is a *second proxied HTTP(S) endpoint* (e.g. an admin UI on a different container port). Direction:

```toml
[port.web]
container = "$PORT"          # default: proxied on 443 by the app's hostnames

[port.admin]
container = 9090
proxy     = true            # nginx proxies this endpoint
subdomain = "admin"         # served at admin.<host>; inherits TLS
```

Each proxied secondary endpoint is exposed as a subdomain of the app's primary host and inherits its TLS. Raw, non-HTTP ports stay in `[[ports]]`. The full routing mechanism (subdomain vs path) is an extension of ADR 040; this ADR fixes the *config shape* and the principle (no app binds 80/443 directly; the proxy multiplexes), and the mechanism — nginx rendering, the loopback-only invariant, and the multi-SAN cert requirement — is fully designed in **Phase 2 (P2.4)** alongside `external_ip`.

### 5. Deploy ignore patterns — `[build].ignore`, not `.hop3ignore`

Deploy-time ignore patterns (what *not* to bundle and upload) are configuration about the app, so by the same tenet — *declare intent in `hop3.toml`, not a sidecar* — they belong in `hop3.toml`, not a Hop3-invented dotfile.

Today the surface is split and inconsistent:

- The **CLI bundler** (`hop3-cli` `arguments.py`) reads patterns from a `.hop3ignore` file (`IGNORE_FILES = [".hop3ignore", ".gitignore"]`). This is the live mechanism.
- The **schema** already declares `[build].ignore` (an inline list) and `[build].ignore-file` (a pointer to a file), but the server-side getters (`Hop3Config.ignore_patterns` / `ignore_file`) have **no consumers** — they are unwired. And `[build].ignore-file = ".hop3ignore"` is the worst shape of all: a `hop3.toml` field whose value is "go read this other file."

Decision:

- **`[build].ignore`** (an inline list of glob patterns in `hop3.toml`) is the single canonical, method-agnostic way to declare what is *not* part of the app:

  ```toml
  [build]
  ignore = ["*.log", "node_modules/", "tmp/", ".env"]
  ```

  It applies regardless of how the app reaches the server, and is the primary mechanism for the `hop3 deploy` upload path (where the CLI tars the working tree).

- **A built-in default ignore set always applies** (and `[build].ignore` extends it): VCS metadata and dependency/cache dirs the server regenerates — `.git/`, `node_modules/`, `.venv/`, `venv/`, `__pycache__/`, `*.py[cod]`, `.idea/`, `.DS_Store`, `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, `*.egg-info/`. This is what makes dropping the old `.gitignore` upload-fallback safe: the common junk is excluded with zero config, so most apps need no `ignore` at all.

- **Remove `.hop3ignore`** (the Hop3-invented sidecar) and **remove `[build].ignore-file`** (the pointer field — it just re-introduces a sidecar). The CLI bundler reads `[build].ignore` from `hop3.toml` before packaging the upload, instead of `.hop3ignore`.

- **Standard ecosystem ignore files apply only in their native context — never for the generic `hop3 deploy` upload:**
  - **`.gitignore` → git-push deployment only.** With a `git push` deploy the transport *is* git, so `.gitignore` already governs what reaches the server (ignored/uncommitted files never arrive); Hop3 does nothing special. It is **not** consulted for the `hop3 deploy` upload.
  - **`.dockerignore` → the `docker` builder.** When the deployment method is Docker, the build context is filtered by `.dockerignore`, the standard, well-understood file Docker already honors. Hop3 leaves that to Docker.

  These are real, ecosystem-standard files tied to a specific transport/builder — not Hop3 inventions — so honoring them in their own context surprises no one. `.hop3ignore`, by contrast, was a Hop3-specific sidecar for the *generic* upload, and that role now belongs to `[build].ignore`.

This also wires up config that is currently dead: the unwired server getters either move to the CLI (the real bundler) or are removed.

## Phase 2 Design — Deferred Features

Phase 1 shipped each capability in its no-privilege, no-extra-dependency form (host symlinks for `persist` volumes, Docker-native limits, on-demand backups). The deferred items below complete the surface; they are designed here so the "Not yet implemented" list points at *specifications*, not blanks. Every one keeps the Phase-1 tenets — declare intent, realize idempotently, **fail loud and never fake success**, and tear down completely *and verifiably*. The designs were validated by an adversarial pass; the blocker findings are folded in inline (re-attach after respawn, visibility of failed scheduled backups, teardown over live mounts/cgroups, and the single shared rootd amendment).

Three items — native `tmpfs`/`bind` mounts and native `[limits]` enforcement — cross the kernel privilege boundary and so depend on one hop3-rootd amendment (P2.0). The other two — backups and networking — need **no** new privilege and ship first.

### P2.0 — One combined hop3-rootd amendment (extends ADR 041)

Native volumes and native limits both need privileged kernel operations hop3-rootd does not expose today (its v1 ops are `firewall.*` / `nginx.*` / `daemon.*`, and its unit is locked to `CapabilityBoundingSet=CAP_NET_ADMIN`, `ProtectControlGroups=true`, `PrivateMounts=true`). Rather than two separate, drifting extensions, ADR 041 gains **one** Phase-2 amendment introducing both op families behind a single client/state/validation contract:

- **`mount.*`** — `mount.tmpfs({mountpoint, size_bytes, mode, app_name})`, `mount.bind({source, mountpoint, mode, read_only, app_name})`, `mount.unmount({mountpoint, app_name})`, `mount.list({app_name?})`.
- **`cgroup.*`** — `cgroup.ensure_slice()`, `cgroup.set_limits({app_name, memory?, cpu?, processes?})`, `cgroup.attach_pids({app_name, pids})`, `cgroup.remove({app_name})` (kills the subtree, then rmdir), `cgroup.read({app_name})`.

What makes it *one* amendment rather than two: **one path-allow-list** (rootd re-derives `APP_ROOT` and runs the existing `validate_app_name` for both families; every `mountpoint`/leaf must canonicalize under `<APP_ROOT>/<app>/src/` resp. `hop3.slice/hop3-app-<app>.scope` — callers never pass arbitrary paths); **one state file + reconcile loop** (mounts and cgroup leaves join `firewall`'s atomic-write/reconcile discipline, so a rootd restart re-asserts or cleans exactly what it owns); and **one unit-hardening threat model** — the union `CAP_SYS_ADMIN` (mounts) + `MountFlags=shared`/non-private namespace (so an app's Emperor-spawned process can actually *see* a mount made by rootd) + `ProtectControlGroups=false` or a delegated `hop3.slice` is a materially larger trust budget than CAP_NET_ADMIN-only and must be threat-modelled as a whole. **If that amendment is rejected, native tmpfs/bind and native limits are infeasible and only the Docker paths ship** — that is the guaranteed-shippable baseline, stated up front.

Hard invariant: the Phase-1 guards (`realize_volumes`' "not implemented" raise for tmpfs/bind; `_reject_limits_on_non_docker`) **stay until the matching rootd ops exist**. Removing a guard before enforcement is real would let an app deploy *looking* capped/persisted but not — the exact lie this ADR forbids — so the guard's removal is gated on the op being registered.

### P2.1 — Volumes: `tmpfs`, `bind`, and Docker `[[volumes]]` (extends §2)

`realize_volumes` becomes a dispatcher over `type` (`persist` shipped; `tmpfs`/`bind` added), still aborting on an unknown type.

- **`tmpfs`** — a sized RAM mount at `src/<target>` (a real kernel mount, not a symlink). `size` becomes **required** for tmpfs and is format-validated like `[limits].memory` (an uncapped tmpfs defaults to half of RAM — a multi-tenant footgun, so a sizeless tmpfs aborts at schema time); a cross-section validator rejects `Σ tmpfs size ≥ [limits].memory`. Never seeded (scratch; shadowed shipped content is *logged*, not silent) and **never backed up** (`_backup_volumes` skips `tmpfs` regardless of `[volumes.backup]`, which is itself a config error on a tmpfs). Native: rootd `mount.tmpfs`; Docker: a compose `tmpfs:` mount (counted against `mem_limit`).
- **`bind`** — adds a `source` field (absolute host path; the deliberate inverse of the relative `target`). **Default-deny:** only paths under an operator allow-list (`HOP3_BIND_VOLUME_ALLOWLIST`, empty by default) are accepted, with the `source` `realpath`-resolved and re-checked against the resolved allow-list in *both* hop3-server and rootd (no symlink escape). Two apps binding the same source is the unmanaged-shared-resource hazard, so a new `BindClaim` registry (mirroring `PortClaim`) detects contention and aborts. Backups **default-exclude** bind sources (operator-owned, possibly shared/huge); opt in with `[volumes.backup] include = true`. **Destroy must never delete the source:** the bytes live at `source` outside `app_path`, so once unmounted the mountpoint is just an empty dir — but a *still-mounted* bind makes `rmtree(app_path)` follow into operator data, which the teardown gate below prevents.
- **Docker `[[volumes]]`** — removes `_reject_volumes_on_docker`. Instead of host symlinks (invisible to a container), the compose generator bind-mounts the **same** host dir `<app>/volumes/<name>` into the container at `target`, so the host-side backup/restore path is byte-for-byte unchanged regardless of builder. Seed-once for Docker copies the image's content at `target` into an empty host volume via a throwaway `docker create` + `docker cp` (a `docker cp` failure other than "path absent in image" aborts — no silent empty volume). bind/tmpfs map to compose `volumes:`/`tmpfs:`.

**Teardown gate (blocker fix).** `App.stop()` (before src/ is wiped) and `App.destroy()` (before any `rmtree`) must, for every declared native mount: reap processes, `mount.unmount` (lazy `MNT_DETACH` fallback on EBUSY), then `mount.list({app})` and **raise if any survive** — refuse to delete over a live mount. Covered by a test with a deliberately-busy mount. Docker releases its own mounts when the container dies, and `compose down --volumes` never touches a host bind source.

### P2.2 — Limits: native enforcement, server-wide default + ceiling, best-effort (extends §3)

How native apps run dictates the mechanism: a native app is *not* its own systemd unit — one Emperor (`uwsgi-hop3.service`) runs every app's worker as an `attach-daemon` `exec`. So the §3 "per-app systemd slice" phrasing was aspirational; the real surface is a **per-app cgroup v2 leaf** (`hop3.slice/hop3-app-<name>.scope`) that rootd creates and into which the app's PIDs are migrated, independent of who spawned them. Mapping mirrors Phase-1 Docker: `memory→memory.max` (plus `memory.swap.max=0`, so a cap is a real cap, not spill-to-swap), `cpu→cpu.max` (`round(cpu*100000) 100000`), `processes→pids.max`. cgroup v2 only; v1/hybrid hosts fail loud and the installer records cgroup-v2 as a host fact. For parity, Phase-1's Docker mapping also gains swap-off so OOM timing matches across builders.

**Keeping respawns capped (blocker fix).** An Emperor-respawned worker gets a fresh PID not in the leaf; the existing state-sync service only loops *transitional* apps, so a RUNNING app's respawned worker would silently escape its cap. Memory enforcement therefore uses a **cgroup-enter shim**: the worker's `exec` is wrapped so each (re)spawned PID writes itself into `cgroup.procs` *before* `exec`-ing the app — the leaf is the entry gate, not a post-hoc attach. A periodic reconcile over **all RUNNING apps** (not just transitional) backstops cpu/pids, and the leaf persists across a redeploy's stop→rebuild→start so there is no uncapped window.

**Server-wide default + ceiling** — two operator settings on `HopConfig`, both off by default (single-tenant boxes and the test suite are unaffected): a per-dimension **default** applied where an app declares nothing, and a per-dimension **ceiling** (the multi-tenant safety net). A declared value above the ceiling **aborts** — never silently clamps down, because silently giving an app less than it asked for is the same class of lie as not enforcing. Resolution is a pure `resolve_limits(declared, defaults, ceilings)` transform feeding both the cgroup ops and the Phase-1 Docker mapping, so defaults/ceilings apply uniformly.

**Modes & surfacing.** Strict (default): any unenforceable declared/defaulted limit aborts. Best-effort (operator opt-in): the app runs, but the unenforced state is recorded on the App row (`limits_enforced`/`limits_detail`) and shown in `hop3 app status`/`debug` in warning colour, at the same prominence as a CRASHED row, plus a red deploy-time warning — never a clean "deployed." A declared value over the ceiling aborts in **both** modes (it's a config error, not an enforcement gap). OOM kills are surfaced via `memory.events::oom_kill` in status and a deploy-time `Diagnosis`. **Teardown:** `destroy` calls `cgroup.remove` and verifies the leaf is gone (raises otherwise); `cgroup.kill` becomes a stronger reap surface than `/proc` scanning for the Nix-store `exec` heisenbug.

### P2.3 — Backups: scheduled, retained, `paths`/`exclude`, per-addon (extends §4a)

**Scheduler: in-process, not systemd timers or cron.** A fourth background service in the ASGI lifespan, structurally identical to `CertRenewalService`/`StateSyncService`/`DomainHealthService` (a daemon thread + stop-event + a testable `run_once()`), polling every 60s. It needs no rootd and no new dependency, and — crucially — leaves **no per-app host artifact**: a systemd timer or `/etc/cron.d` entry would survive `destroy` (a leftover, hence a platform bug). "Did the cron minute elapse" is computed from the existing `Backup` rows, so no new scheduling table.

**Schema** promotes `BackupSection` to the policy the docs already describe (reconciling the §4a doc/schema mismatch): `enabled` + `schedule` (5-field cron, UTC; required when `enabled`) + `[backup.retention]` (`days` / `keep-last`) + the now-wired `paths`/`exclude`, plus a strict `[addons.backup]` (`method`/`schedule`/`retention`). All `extra="forbid"`, all fail-loud at schema time. The cron matcher is stdlib-only (no `croniter`).

**Failed scheduled backups must be visible (blocker fix — a requirement, not an open question).** A FAILED backup writes no manifest and `create_backup` rmtrees its partial dir, while the current list reads manifests and hardcodes status `COMPLETED`. The read path (`list_backups` / `BackupListCmd` / dashboard) **must** read `state` plus a new `error` column from the `Backup` DB rows (the authoritative source) and merge manifest detail only for COMPLETED rows. This change is sequenced **first** — without it a failed scheduled backup is fire-and-forget to `/dev/null`. The scheduler catches per-app (one failure doesn't stop the cycle) but logs red, leaves the row FAILED+`error`, and refuses to start a second backup while a STARTED row exists for the app (no overlap). A `scheduled` provenance flag distinguishes manual from scheduled backups, and an "overdue" line (newest scheduled COMPLETED vs the cron) surfaces a scheduler that silently stopped.

**Retention** runs in the same cycle: prunes only `scheduled, COMPLETED` backups by `days` (finally consuming the dormant `expires_after` field) and/or `keep-last` (the more conservative when both are set), via `delete_backup` (directory + row together), and **always excludes the single most recent good backup** from deletion — logging yellow when it keeps one against policy, never silently leaving zero. **`paths`/`exclude`** wire into `_backup_source`/`_backup_data` (the exclude glob composes into the existing tar `filter`, with the volume-link drop keeping precedence; `paths` archived as a separate `extra.tar.gz` so restore doesn't lose them to the redeploy's `git clean`); a declared-but-missing `paths` entry **aborts** the backup (no silent omission, mirroring `_app_volumes`). Per-addon `method` validates against a new `supported_backup_methods` capability on the addon protocol (fix-the-class, not per-type knowledge in the manager). **Teardown:** `destroy` must rmtree `BACKUP_ROOT/apps/<app>/` (the FK cascade drops rows; the directories are otherwise a disk leftover) — verifiable.

### P2.4 — Networking: `external_ip`, proxied secondary endpoints (extends §1b / §4b)

**`external_ip`** resolves at step 5 of the env pipeline (like other refs) and is re-resolved each deploy — a host *fact*, never generated-once. Determination is sovereignty-first: (1) operator-set `HOP3_EXTERNAL_IP` / `_IP6`; (2) default-route detection (`ip route get` `src`, a kernel-local probe with no egress, factored into a shared `netinfo` helper); (3) an opt-in `HOP3_EXTERNAL_IP_ECHO_URL` (https-only), off by default — the platform never phones home to learn its own address unless told to. A detected private/loopback/link-local address is **not** returned as public — it fails loud, because returning a private address as `PUBLIC_IP` is fake success. This means auto-detection is best-effort for bare-metal/non-NAT only; **cloud/NAT boxes must set `HOP3_EXTERNAL_IP`**, and the error message says exactly that. `family = "v4"|"v6"` selects.

**Proxied secondary HTTP endpoints** — the missing "second proxied HTTP port" (e.g. an admin UI); raw non-HTTP ports stay in `[[ports]]`. `PortConfig` gains `proxy`/`subdomain`/`path` while **keeping** its shipped `container`/`public`/`https` fields (additive, no break): a named endpoint with `proxy = true` requires exactly one of `subdomain` (served at `<sub>.<host>`) or `path` (served at `<host><path>`, rendered ahead of `location /`). nginx renders the endpoint into the **same** `<app>.conf` (one atomic teardown unit) as an extra `server{}` (subdomain) or `location{}` (path). The container port is reached on loopback — native: the app binds `127.0.0.1:<container>`; Docker: publish `127.0.0.1:<hostport>:<container>` — and a post-start probe **asserts the port answers on loopback AND is refused on a non-loopback address**, so a publicly-bound secondary listener (bypassing nginx/TLS) aborts the deploy rather than silently exposing an admin UI. **TLS:** a `subdomain` adds a hostname the served cert must cover, so issuance must become **multi-SAN** (the self-signed engine accepts a name list; certbot adds `-d` per name), and `verify_cert` runs over **every** secondary FQDN so a missing SAN fails loud rather than serving a mismatch. Teardown is already complete (same conf file, same cert pair); Docker must verify the published loopback port is released so it can't block the next deploy's `get_free_port`.

### Phase 2 build order

1. **No new privilege — ship first:** the backup read-path fix (DB rows + `error` column) → scheduler / retention / `paths` / `exclude`; `external_ip`; `path`-mode secondary endpoints; Docker `[[volumes]]` (compose bind-mounts, no rootd).
2. **The ADR 041 amendment (P2.0):** the combined `mount.*` + `cgroup.*` families under one threat model. Until merged, the Phase-1 guards stay.
3. **Unlocked by P2.0:** native `tmpfs`/`bind` volumes; native/Nix `[limits]` enforcement (then `_reject_limits_on_non_docker` is removed) plus server-wide default/ceiling and best-effort mode.
4. **After multi-SAN cert issuance:** `subdomain` secondary endpoints (they fail loud until then; `path` mode covers the interim).

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

> **Builder support today:** `[[volumes]]` is realized on the native/Nix builders and `[limits]` is enforced on the Docker builder, so this *combined* form is not deployable on a single builder yet — the deploy aborts loudly rather than half-applying. The snippet documents the Phase-1 target; until both features share a builder, declare them in apps that use the matching builder. See Implementation Status.

## Consequences

### Positive

- Closes the four gaps; removes the per-app workarounds the ethos warns against.
- Fixes the silent-drop bug — config is honored or rejected, never quietly ignored.
- Generated-once secrets make first-boot reproducible and redeploys idempotent.
- Declarative persistence makes stateful apps survive redeploys by design, not by luck.
- Per-app limits make the multi-tenant single box production-safe.
- Aligns the documented format (ADR 002) with the runtime, and the docs with the schema.

### Negative

- Schema complexity: `[env]` gains a discriminated union; new sections to validate and test.
- New realization paths (volume linking, cgroup wiring) with OS variance, several depending on hop3-rootd (ADR 041) — a hard dependency for limits and bind/privileged mounts.
- A behavior change at the edge: dict-valued env entries silently ignored today will now be interpreted or rejected; a few existing configs may surface previously-dead entries (documented in Backwards Compatibility).
- Touches several existing ADRs (002 corrected, 016/024 extended, 040 extended).

## Security Implications

- **Secrets**: CSPRNG only (`secrets`); stored encrypted at rest once ADR 011 lands; never logged except a `display = true` one-shot to deploy output (documented, opt-in).
- **`bind` volumes**: host-path escape risk → default-deny with an operator allow-list.
- **Dynamic refs**: resolve only against each addon's documented key contract; no new exposure beyond auto-injection.
- **`external_ip`**: exposes the host's own public IP to its own app — acceptable.
- **Resource limits**: a DoS-mitigation (positive). A declared-but-unenforced limit is a false guarantee → abort by default.

## Backwards Compatibility

- Additive: static `[env]`, existing `[[addons]]`, `[run]`, etc. are unchanged.
- The one change: dict-valued `[env]` entries that are currently dropped will be interpreted (known forms) or rejected at validation (unknown shapes). This is a fix; the migration note will call it out and `hop3 config migrate` / validation will flag affected files.
- ADR 002 status corrected (`from`/`key`/`random` were never shipped). ADR 016 and 024 extended for resource-aware backup policy; ADR 040 extended for proxied secondary endpoints. No deployed app breaks.
- **`.hop3ignore` is deprecated** in favour of `[build].ignore`, and `[build].ignore-file` is removed. Transition: a present `.hop3ignore` is still honoured for one release with a loud deprecation warning that points to `[build].ignore`, then dropped (no silent shim). The CLI's current `.gitignore` fallback for the `hop3 deploy` upload (`IGNORE_FILES = [".hop3ignore", ".gitignore"]`) is also removed — `.gitignore` belongs to the git-push path, not the upload path. Migration for an existing `.hop3ignore` user: move its patterns into `[build].ignore`. git-push users (relying on `.gitignore`) and Docker users (relying on `.dockerignore`) are unaffected.

## Alternatives Considered

- **Adopt Nua's inline-dict env model wholesale** (`{from, key, random}` as the primary mechanism, injection opt-in). Rejected: auto-injection is more ergonomic for the overwhelmingly common single-database case; the hybrid keeps that and adds power only where needed.
- **Secrets only via `hop3 config set`.** Rejected: cannot run before the first deploy, which is exactly when boot-crashing releases (Phoenix) need the value; not reproducible from the repo.
- **Regenerate secrets every deploy.** Rejected: non-idempotent; rotates sessions/keys and corrupts data on every redeploy.
- **Resource limits via uWSGI knobs only.** Rejected: incomplete and runtime-specific; the cgroup/systemd boundary is the real enforcement surface and covers Docker/Nix too.
- **No volumes; rely on the implicit `data/`.** Rejected: apps cannot declare which tree paths persist, forcing bespoke layout hacks.

## Prior Art

- **Nua `nua-config`**: `[[volume]]` (managed/directory/tmpfs/remote), `{from/key/random/external_ip}` env, `[docker].mem_limit`, per-resource backup.
- **Heroku**: config vars; no persistence (we go further with volumes).
- **Docker Compose**: `volumes`, `mem_limit`/`cpus`, per-service config.
- **Kubernetes**: Secrets, PersistentVolumeClaims, resource requests/limits — the conceptual model for declare-and-reconcile.
- **systemd resource control**: `MemoryMax`, `CPUQuota`, `TasksMax` — the native enforcement mechanism.

## Unresolved Questions

- Secret rotation UX (`hop3 config rotate KEY`?).
- Per-context (ADR 042) overrides for volumes / limits / generated secrets — likely desirable; deferred.
- tmpfs/bind and cgroup enforcement on non-systemd OSes — Phase 2 (P2.0/P2.2) flags this as the open feasibility risk: the demo runs rootd under supervisor, so systemd cgroup *delegation* is unavailable there and the "rootd writes `hop3.slice` directly" path is unproven.
- Multi-port proxying — *resolved* in Phase 2 (P2.4): `path` mode ships first (shares the primary cert), `subdomain` after multi-SAN issuance lands; the per-endpoint healthcheck shape and a `$PORT`-style dynamic secondary port remain open.
- The server-wide default limit — *resolved* to **off by default** in Phase 2 (P2.2); the recommended value for a multi-tenant box, and whether to flip it on once mature, remain open.

## Future Work

- **Source-acquisition-by-config**: generalize the Nix `url` + `sha256` story to `[build]` `src-url` + `src-checksum`, `git-url`/`git-branch`, and `base-image` + `method = "wrap"` (deferred from Phase 1).
- **Descriptive metadata**: `tagline`, `release`, `profile` (low priority).
- **Addon version pinning** and a `mongodb` addon type.
- `hop3 config rotate` for secret rotation.

## References

- `local-notes/nua-vs-hop3-config-comparison.md` — the gap analysis that motivated this ADR.
- ADRs 002, 003, 011, 016, 024, 035, 040, 041, 042, 045.
- Nua specs: `sandbox/nua/doc/src/dev/specifications/{nua-config,configuration}.md`.
- Python `secrets`; systemd resource control; Docker resource constraints.
