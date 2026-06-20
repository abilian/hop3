# Hop3 Test Lab v2 — Specification (direction)

**Status:** v2 design draft (2026-06-18) · **Builds on:** [`testlab-specs.md`](testlab-specs.md) (as-built v1) · **Implements forward:** [ADR 044](../../notes/adrs/044-nightly-test-lab.md) §M6+ · **Type:** subproject spec (forward-looking)

This is the **v2 direction**: where the Test Lab goes beyond the shipped v1 (one box, nightly, refuse-if-busy). It is a design, not as-built — each section says what changes from v1 and what's new. v1 stays the substrate; v2 is additive where it can be.

## 0. The shift in one paragraph

v1 is a *nightly test lab* bound to one Hetzner box, driven by an in-process scheduler, that refuses a second run while one is live. v2 is a **specialised CI platform**: the Lab **runs on a remote cloud server**; users drive it from a **thin `hop3-testlab` client** (nothing runs locally); run-requests are **queued** (viewable, removable); the suite is pulled from **one or more git sources** (incl. private repos) at a chosen **branch**; runs target a **pool** of boxes so two can run in parallel; and the whole server is configured by **one TOML file**. The daily job — check every app in the main repo (and other repos) once a night, plus ad-hoc runs — is the headline use case.

---

## A · Architecture: four loosely-coupled pieces

The Test Lab system is **not one program** — it's four pieces that *currently share this monorepo out of convenience, not necessity*. Each can be versioned, sourced, and (later) split into its own repo/release independently. Getting the boundaries right is the load-bearing decision of v2; most of §1–§10 are consequences of it.

| Piece | What it is | Lifecycle | Versioned / sourced by | In-repo today |
|-------|------------|-----------|------------------------|---------------|
| **1. Testlab server** | The control plane: web UI + API + queue + dispatcher + scheduler + result store. Orchestrates and records; **runs no tests itself.** | Long-lived, **stateful** (owns the queue + store) | its own release (`hop3-testlab`) | this package |
| **2. Test runner** | The engine: given (platform, apps, target), deploy + verify + write results. | **Ephemeral** per run, stateless but for the store write | a versioned dependency (`hop3-testing`), invoked as `hop3-test system …` | sibling package |
| **3. System Under Test** | deployer + installer + hop3-server, as **one cohesive set** — the platform being validated. | An **input**: installed onto the target at a chosen ref per run | a **git ref** (main / devel / tag / PR SHA) | the other packages — *currently entangled*: the deploy uses this repo's own code/branch |
| **4. Apps** | The test corpus: production/advertised, experimental, public, private/customer. | An **input**: fetched per run, a selector resolves a subset | **git sources × ref** (§4), per source | `apps/`, `demos/` dirs — but designed to come from many repos |

**A run is a composition of independently-versioned inputs.** Read it as one sentence:

> `runner@v` deploys `apps(source@ref, selector)` against `platform@ref` on `target`, orchestrated and recorded by `testlab-server@v`.

The dashboard's real job is to answer *"which composition failed"* — so every run must record the **full provenance tuple**: testlab-server version, runner version, **platform ref**, and **each app-source ref**. `TestRun` today has `hop3_version` + `git_sha` (the platform, partially); v2 must add the runner version and per-source refs.

**Consequences (these drive the rest of the spec):**
- **The platform is "just another source"** whose build artifact is *an installed platform on the target box* rather than an app to deploy. So #3 (run against main vs devel) is structurally identical to #4 (app sources): both are "fetch `source@ref`, then act." Treat them with the same machinery.
- **Don't bake monorepo assumptions.** No hardcoded `../../apps`, no `hop3_version = my own package version`, no "the platform I test is my own SHA." Each piece is addressed by **(source, ref)**, not by "my sibling on disk." This is exactly the coupling v2 breaks.
- **The decoupling *is* the product** — it's what makes the CI matrix possible: same apps × {main, devel} (did a platform change break apps?); a new/private app source × a *stable advertised* platform (does the customer's app work on shipped hop3?); a platform PR × the full advertised corpus (the regression gate). v1 can express none of these because all four pieces are pinned to one repo at one SHA.

---

## 1. Defining change — server-resident, client-driven

**v1:** `hop3-testlab run` calls `worker.run_once` in-process on the local machine.
**v2:** the Lab is a server on a remote box; `hop3-testlab` is a **client** that submits commands over the wire. Mirrors the existing **hop3-cli ↔ hop3-server** transport (JSON-RPC over HTTP, optionally SSH-tunnelled) — consistent with the "mirror hop3-server's stack / dogfood as a Hop3 app" constraint.

Two binaries, one package:
- **server** — `hop3-testlab serve` on the cloud box: web UI + API + queue + dispatcher + worker(s).
- **client** — `hop3-testlab run|queue|status|...` on a laptop/CI: authenticates, POSTs a run-request, prints the result. **Executes nothing locally.**

Cascading consequences (these drive §4–§8):
- **Selectors resolve server-side.** `hop3-testlab run coverage 'apps/my-apps/*'` sends `{mode: coverage, selector: "apps/my-apps/*"}`; the server expands the glob against a **source repo's** tree, not the client's disk. The pattern must be **quoted** so the local shell doesn't expand it against laptop files that don't exist.
- **The client must authenticate** to the server → §8 (a CLI token, sibling to the web magic-url).
- **A run-request is enqueued, not run inline** → §3.

**New API surface (v2):** an authenticated `POST /api/runs` (enqueue), `GET /api/queue`, `DELETE /api/queue/{id}`, `GET /api/runs/{uid}` — the machine-facing counterpart to v1's session-cookie web UI. This is the bearer/token API that v1 deferred (v1 §9/§14).

---

## 2. Run lifecycle (v2)

```
client: hop3-testlab run coverage 'apps/my-apps/*' --source main-repo --branch devel
   │  (HTTP + token)
   ▼
server API: validate + enqueue a RunRequest row (status=pending)        ← §3 queue
   ▼
dispatcher: pick the oldest pending request whose target is free,        ← §3 + §6 pool
            acquire that target's lease, mark dispatched
   ▼
worker (per target): fetch source@branch → resolve selector to a test    ← §4 + §5
            set → blank-slate the box → spawn the engine subprocess
   ▼
engine (hop3-testing): run + write results/bundles to the shared store   ← unchanged from v1
   ▼
web UI + client poll the store for status/result                         ← v1 read path
```

The **engine and store stay v1's** (one engine, one store). v2 adds the queue, the dispatcher, source-fetching, and the client/server split *around* that core.

---

## 3. The queue + dispatcher (the spine) — and build-vs-arq

**v1:** a single non-blocking **lease** per target; a second request is refused (`?run=busy`).
**v2:** requests are **queued**, not refused. A **`RunRequest`** is durable domain data — the queue is just rows the dashboard already knows how to show; #2's "view / remove from queue" falls out for free.

`RunRequest`: `id`, `created_at`, `actor`, `trigger`, `source`, `branch`, `mode`, `selector`, `target` (or "any"), `status` (pending|dispatched|running|done|cancelled), `run_uid` (once dispatched), `priority`. Cancelling a pending request = a row update; cancelling a running one = the existing PID/lease **stop control**.

**Queue store vs execution runtime — keep them separate.** The *queue state* lives in the DB (domain data, dashboard, audit). The *runtime* is a process that dispatches pending requests to free targets and runs them. Two options for the runtime:

| | DB queue + worker-process poll loop | arq (Redis) |
|---|---|---|
| New dependency | none (DB already there) | Redis (already a Hop3 addon, so cheap) |
| Queue visible to dashboard | **yes, same store** | no — lives in Redis; must mirror into DB for #2 |
| Worker out of web process | yes (dedicated process) | yes |
| Cron (nightly) | reuse APScheduler, or the loop | **arq cron folds it in** — one system |
| Retry/backoff, job timeout, abort | hand-rolled (v1 already kills by PID) | **batteries included** |
| Lines to first version | ~50 | ~same, + Redis ops + async |

**Recommendation:** start with the **DB queue + a dedicated worker-process poll loop** — the queue is the durable record the UI shows, it's one fewer daemon to secure on the box, and 2 targets don't need arq's throughput. **Move execution out of the web process now** regardless (v1's in-`serve` scheduler is the fragile bit to fix). **Adopt arq** when you want many workers, retry/backoff, or its observability — at that point Redis is already available and the DB `RunRequest` table can become arq's job source of truth (or be mirrored). *This corrects the v1-era "arq deferred, don't bother" stance: arq is a legitimate runtime, just not required at N=2, and not a substitute for keeping queue state in the DB.*

---

## 4. App sources — git repos, including private

**v1:** the catalog scans **local directories** (`catalog.py` over the engine's scanner).
**v2:** the Lab knows a set of named **sources**, each a git repo it clones/fetches **server-side**:

```toml
[[source]]
name   = "main-repo"
url    = "https://github.com/abilian/hop3.git"
branch = "main"                 # default ref; overridable per run
paths  = ["apps", "demos"]      # where to scan for test apps within the repo

[[source]]
name      = "private-apps"
url       = "git@github.com:abilian/customer-apps.git"
deploy_key = "$CUSTOMER_APPS_DEPLOY_KEY"   # private repo → key from the single TOML (§7)
```

A run-request names a source (default: `main-repo`) and a ref; the worker checks out `source@ref` into a per-run workspace, builds the catalog from `paths`, then resolves the selector (§5) against that tree. This is what makes #3 (run main vs devel) and #7 (server-side selectors) actually work, and keeps the apps off the client entirely.

**Caching:** clone once, `git fetch` + checkout per run (keyed by source). Private repos authenticate with a deploy key stored only in the server's TOML, never in the DB.

---

## 5. Run selection & dynamic subsets

**v1:** fixed modes (`smoke|ci|curated|coverage|nightly|full`) + saved **profiles**.
**v2:** a **selector** resolved server-side at enqueue/dispatch against the checked-out source:
- **path glob** — `apps/my-apps/*` (the #7 case), expanded against the source tree.
- **mode** — the v1 modes, kept.
- **dynamic subset (#5)** — computed, not enumerated: by `covers=[...]` tag, by variant (docker/nix/native/template via `discriminators.py`), by "changed since `<ref>`" (diff the source between two refs → only affected apps), or a representative coverage sample. The selector returns a concrete test set; the run records `planned_counts` (a column that already exists) so the dashboard shows what was selected and why.

"Changed-since" + per-source branch is the piece that turns this into a real CI: a push to `devel` → run only what changed.

---

## 6. Parallelism & the pool

**v1:** one target; the lease is **already per-`target_id`** (the seam).
**v2:** a **pool** of targets (≥2 Hetzner boxes, or Hetzner + Docker). The dispatcher (§3) assigns each pending request to a **free** target — N targets ⇒ N concurrent runs. No new concurrency primitive: it's the existing lease, once per target, plus the dispatcher loop.

**The real blocker is not the second box — it's the store's single-writer assumption.** v1 §7/G7 notes the writer is "fine because single-target, single-writer." Two engine subprocesses writing one **SQLite** store concurrently breaks that. Resolve before enabling parallel runs:
- **Move the store to Postgres** (the `DATABASE_URI` seam exists, unexercised) — preferred for a multi-writer CI server; **or**
- **run-id-parameterized incremental writes** (G7) so concurrent writers don't stomp `self._current_run`.

Until one of those lands, the dispatcher must cap concurrency at 1 (degrade *loudly* to "queued behind the running job", never silently serialise while claiming parallelism).

---

## 7. Configuration — one server TOML

**v1:** split across `cloud_config.toml` (hetzner/ssh/schedule/retention) **and** env-driven `TestlabConfig` (user/pw/secret/db).
**v2:** **one server TOML** is the single source of truth on the box — folds `TestlabConfig` in, adds `[[source]]` and the pool:

```toml
[server]      # was TestlabConfig: bind, database_uri, secret_key, retention
[auth]        # admin identity; magic-url + CLI token settings (§8)
[[target]]    # pool members: hetzner (api_token, server_id, image, ssh_key) | docker | ssh host
[[source]]    # §4
[schedule]    # nightly cron (target, ref, mode, time)
```

`$ENV_VAR` expansion stays (12-factor for secrets). Env vars remain a *fallback*, not a second config system. The **client** has its own tiny config — `~/.hop3/testlab/client.toml`: `server_url` + `token` — and nothing else.

---

## 8. Auth — magic-url (web) + token (CLI)

**v1:** session-cookie + a single admin password.
**v2:** two front doors, one identity:
- **Web — magic URL (#1).** A server-side CLI (`hop3-testlab login-url`, run on the box by whoever has shell) mints a **signed, single-use, short-TTL URL**; opening it establishes the session. No shared password to leak; issuance requires server access. (Signing key = `[auth].secret_key` from the TOML.)
- **CLI — token.** The client sends a bearer token (the API surface from §1). Minted by `hop3-testlab issue-token` on the server, pasted into the client's `client.toml`. Same identity model, machine-shaped.

Both reuse v1's CSRF/session plumbing for the browser; the token path is the new bearer API v1 deferred. **Carried forward unchanged:** bundle **secret redaction** is still the top open security item (v1 §12) and becomes *more* pressing once private-repo logs flow through a shared server.

---

## 9. What's reused vs what changes

| Area | v1 (as-built) | v2 |
|------|---------------|-----|
| Engine + result store | `hop3-testing`, one engine/store | **reused unchanged** (Postgres for parallel, §6) |
| Read path / dashboard / trends / bundles | `RunsRepository`, controllers, templates | **reused**; + queue views |
| `worker.run_once` (lease, blank-slate, subprocess, stop) | local, in-process | **reused** as the per-target executor, now driven by the dispatcher |
| Scheduler | APScheduler *inside* `serve` | **moves out** to the worker process; cron enqueues a `RunRequest` |
| CLI `run` | runs locally | becomes a **client** → `POST /api/runs` |
| Catalog | local dirs | server-side **git sources** (§4) |
| Config | two sources | **one server TOML** + tiny client config (§7) |
| Auth | password + session | **magic-url + token** (§8) |
| Concurrency | refuse-if-busy | **queue + pool** (§3/§6) |

v2 is mostly *additive*: a queue/dispatcher in front of `run_once`, a source-fetch step before the catalog, a client/API split, and config consolidation. The engine, store, read path, and the worker's hard-won teardown/stop logic survive.

---

## Requirements refinement (2026-06-18)

Direction from the user, refining §5 (selection) and §7 (config). Supersedes the prior framing where these were later slices.

- **Postgres is a production requirement, not just a slice-3 seam.** The Lab is deployed on a server, so the store is **Postgres** (concurrent readers + the parallel-runs future). Touches both packages: the engine's `ResultStore` writes the same store, and `create_all`/`_ensure_columns` must be PG-compatible (the SQLite-specific partial-unique index). The Lab is **sync** SQLAlchemy → use **psycopg**, drop the unused `asyncpg`.

- **A profile is `{source, platform_version, selection_rules}`** — the single unit created in the UI and launched with **Start build**. **No manual app selection anywhere**: apps/demos/tutorials are always chosen by *rules*, never a hand-picked list. `selection_rules` **reuse the engine's existing rule machinery** (`modes` + `Selector`, `covers` tags, the type/variant discriminators) resolved against the fetched `source@ref` — not a new DSL; the slice-1 path glob is one rule. **Target is *not* part of a profile** — it's a launch-time / pool choice (*what* to build vs *where*).

- **The old `/profiles` (mode-overrides / curated picker) is scrapped**, replaced by the above. `ProfilesController` + the `~/.hop3/test-modes.toml` override file go. The slice-1 manual `apps=[...]` path (the dashboard per-app trigger, the `apps` list in `run_once`/CLI) is removed as dead weight — selection is rule-based only.

- **UI: create/edit profiles + a Start-build button.** The composition becomes drivable from the web UI (which lives *on* the server — no thin-client needed for it).

- **You never pick a server — the queue does (§3/§6 pulled forward).** A **server pool** is maintained via its own CRUD UI (`Server = {name, target_id, kind, enabled}`; creds stay in config, not the DB). **Start build → enqueue** a `BuildRequest` (no target); the **dispatcher** assigns it to whichever enabled pool server has a **free lease** (`leasing.py` is already per-`target_id` — that's the pool seam) and runs it there. Serial v1 (the dispatcher still *chooses* the server, one running build at a time); **Postgres unlocks parallel** dispatch across the pool (concurrent engine writers need the multi-writer store). The dispatcher runs as an interval job in the in-`serve` scheduler for v1; a dedicated worker process is the later hardening.

**Next slice — "Profiles + Server pool + Queue (UI-driven CI)"**: testlab-owned `Profile`/`Server`/`BuildRequest` models, rule-based selection (reusing `Selector`), profiles + server-pool CRUD, Start-build → enqueue, a dispatcher that picks a free pool server, a queue view, deletion of manual selection + the old profiles — then Postgres → parallel dispatch.

---

## 10. Open questions

1. **Transport:** reuse hop3-cli's exact JSON-RPC client, or a thin HTTP+token client of its own? (Reuse keeps one auth/tunnel story; own client is simpler to evolve.)
2. **Source workspace lifecycle:** clone-cache-and-fetch per source (fast, shared) vs ephemeral clone per run (clean, slower). Disk vs reproducibility.
3. **"Changed-since" baseline (#5):** diff against the source's last *green* run, against the previous ref, or an explicit `--since`?
4. **Parallel store:** commit to **Postgres** for v2 (clean multi-writer) or do the G7 incremental-writer work and stay on SQLite? Postgres looks like the lower-risk path for a CI server.
5. **Queue fairness:** strict FIFO, or priority (nightly full-suite vs a quick ad-hoc `coverage` run)? `RunRequest.priority` is the seam.
6. **arq trigger point:** what concrete signal (worker count, retry needs, observability) flips the §3 recommendation from DB-loop to arq?
7. **Redaction (carried, now load-bearing):** denylist/allowlist for secrets in bundles before private-repo output is viewable on a shared server.
```
