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

Not yet implemented: dynamic env references (`{ from, key }`, `external_ip`), `[[volume]]`, `[limits]`, and the folded-in backup/multi-port extensions.

## Context

Hop3's `hop3.toml` was modeled on Nua's `nua-config` (Hop3's predecessor). ADR 002 reserved a number of Nua-derived fields against future implementation, but several never shipped, and a side-by-side comparison of the two formats (`local-notes/nua-vs-hop3-config-comparison.md`) surfaced four capabilities that Nua expressed declaratively and Hop3 cannot. Each one currently forces a *per-app workaround* — which, by the project ethos, is a signal that the platform is missing something, not that the app is special.

The four gaps, each one a real blocker we have hit while greening the advertised app/tutorial set:

1. **No generated secrets.** Many apps require a secret/key to exist *before first boot* (the release crashes without it). Hop3 has no way to declare "generate a secret named X once and keep it"; the only paths are hardcoding (forbidden) or out-of-band `hop3 config set` / `hop3 deploy --env X=$(...)`. We hit this with Phoenix (`SECRET_KEY_BASE`), Laravel (`APP_KEY`), and Rails (`secret_key_base`).
2. **No declarative persistence.** There is no `[[volume]]`-equivalent. An app cannot declare which paths in its tree must survive the source-replacing redeploy, request a tmpfs, or attach a bind mount. The only persisted location is the implicit `data/` dir.
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
2. A new `[[volume]]` section for **declarative persistence** (Phase 1).
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
MONGO_URL = { from = "database", key = "url" }
APP_FQDN  = { key = "domain" }          # from the app itself
PUBLIC_IP = { external_ip = true }
```

- `from` (optional): name of a declared addon (`[[addons]].name`, defaulting to the app name). Omitted/empty = the app itself, for app facts such as `domain`.
- `key`: the attribute to copy. Each addon type publishes a **documented key contract** — references resolve only against that contract, never against arbitrary internal credentials beyond what auto-injection already exposes.
- `external_ip = true`: the host's detected public IP.

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

### 2. `[[volume]]` — declarative persistence

```toml
[[volume]]
name   = "uploads"          # logical name → storage id "<app>-uploads"
target = "data/uploads"     # path in the app tree (relative) or absolute
type   = "persist"          # persist (default) | tmpfs | bind

  [volume.backup]           # optional; ties into ADR 024
  include = true
```

- `type = "persist"` (default): a directory under the app's data root (`/home/hop3/apps/<app>/volumes/<name>/`), linked into `target` on every deploy. **It lives outside `src/`**, so the redeploy sequence (stop-previous-instance → wipe & re-extract `src/` → `git clean`) cannot touch it; the link is re-established after extract, before start. This is the precise fix for "which tree paths survive a redeploy".
- `type = "tmpfs"`: a RAM-backed dir (`size`, `mode` options) for caches/scratch.
- `type = "bind"`: an operator-approved host path. Binding arbitrary host paths is a host-escape risk, so this is **default-deny**: only paths under an operator-configured allow-list are accepted; anything else aborts the deploy.

Realization by builder: native/Nix → bind-mount or symlink into the app tree via the deploy shell (privileged mounts through hop3-rootd, ADR 041); Docker → container volume/mount. Per-volume `[volume.backup]` makes ADR 024's backup/restore *resource-aware* (a volume becomes a backup unit).

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

**Fail-loud rule.** A *declared* limit is a safety guarantee. If the platform cannot enforce it (rootd unavailable, cgroup controller missing), the deploy **aborts** — it must never start an app that looks limited but isn't (no fake success). An operator may opt into a documented best-effort mode, which then **logs loudly and records** the unenforced state where the user looks.

A server-wide **default limit** (operator-configurable) protects multi-tenant boxes even when an app declares nothing.

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

Plus per-`[[volume]]` `[volume.backup]`. This is the config-surface layer over the backup *system* already specified by ADR 024 (which is extended, not replaced); it supersedes the backup-config sketch in ADR 002.

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

Each proxied secondary endpoint is exposed as a subdomain of the app's primary host and inherits its TLS. Raw, non-HTTP ports stay in `[[ports]]`. The full routing mechanism (subdomain vs path) is an extension of ADR 040 and is detailed at implementation time; this ADR fixes the *config shape* and the principle (no app binds 80/443 directly; the proxy multiplexes).

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

[[volume]]
name = "uploads"
target = "data/uploads"
  [volume.backup]
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
- tmpfs/bind and cgroup enforcement on non-systemd OSes.
- Multi-port proxying: subdomain (chosen default) vs optional path-prefix routing.
- The server-wide default limit value (and whether it is on by default).

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
