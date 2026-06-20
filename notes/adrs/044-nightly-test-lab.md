# ADR 044: Nightly Test Lab — a Web App to Run and Report on the Full Test Suite

**Status**: Draft
**Type**: Architecture
**Created**: 2026-06-05
**Related-ADRs**: 043 (unified-testing-architecture), 041 (privileged-operations-agent), 042 (cli-context-model), 034 (streaming-deployment-logs), 033 (docker-integration), 018 (cli-server-communication)
**Related-notes**: `local-notes/logging-observability.md`

## Context

ADR 043 establishes a **nightly tier**: the full suite (real apps, demos, tutorials, platform e2e) run against real servers, producing an HTML report and finishing overnight. The machinery for *running* that suite already exists in `hop3-testing`: the `DailyTestOrchestrator` (`INIT → RESET → DEPLOY → TEST → REPORT`), `HetznerManager` for provisioning, the `DeploymentTarget` ABC, the catalog scanner, the SQLAlchemy result models, `generate_html_report()`, and the `hop3-test cloud` command that drives them.

What is **missing** is the consumer that makes a nightly run actionable every morning: the result store is effectively write-only (no query API, single-file SQLite), the report is static and trend-blind, and there is no scheduler, no way to browse a failed test's full logs, no trend/flakiness view, and no way to trigger or re-run from a UI. ADR 043 also found that the most common deployment failure — a healthy app behind a 502, the "silent-502" class — is captured by no surface.

This is squarely on the project ethos: *packaging apps is system-validation work; each app is a deliberate probe of the platform's edges.* The nightly suite is the instrument; this app makes its output legible and turns each failure into a visible platform backlog item.

### Why now

ADR 043 makes the nightly data *exist and be uniform* (the shared `collect_diagnostic_bundle`); this ADR builds the product that makes it *visible, queryable, and scheduled*. The two are complementary.

## Goals

1. **Morning status at a glance** — the whole suite's status (apps, docs/tutorials, demos, platform e2e): green/red, counts, duration, and the diff against the previous run (newly-failing / newly-fixed / still-failing).
2. **All the logs for failures** — for any failed test, everything potentially useful: build, app/server, nginx access + error, the journal, the deploy transcript, the HTTP exchange, and the silent-502 proxy probe.
3. **Runs on a Hop3 server, remote-controls Hetzner** — dogfooded on a Hop3 host; provisions and drives Hetzner targets as `hop3-test cloud` does today (other providers later).
4. **Beautiful dashboard + trends** — history, per-app trend lines, flakiness, duration creep — not just a pass/fail dump.
5. **Always under 6 hours** — the run must reliably finish overnight, which over time means scaling out to multiple targets.

## Decision (high level)

Create a new subproject, **`hop3-testlab`**:

| Component | Role | Stack |
|-----------|------|-------|
| **Web service** | Dashboard + JSON API; browse runs, tests, logs, trends; trigger ad-hoc runs | Litestar + Advanced Alchemy + Dishka, server-rendered + HTMX |
| **Scheduler** | Kicks off the nightly run on a timer; enforces the 6 h budget | APScheduler in-process / systemd timer |
| **Runner (worker)** | Provision pool → deploy → run suites → collect bundles → persist → teardown | reuses `hop3-testing` as a **library** |
| **Datastore** | Queryable results + trends | **PostgreSQL** (extends the existing SQLAlchemy models) |
| **Artifact store** | Per-test diagnostic bundles | filesystem volume now; object storage later |

**Key principle: one engine, two front-ends.** The Test Lab does **not** shell out to and parse the `hop3-test` CLI. It imports the `hop3-testing` functional core (orchestrator, targets ABC, catalog, ADR 043's `collect_diagnostic_bundle`) and writes structured results to the shared store. The CLI (`hop3-test cloud`) and the web app are two thin shells over the **same** engine and the **same** store, so a manual CLI run and a scheduled web run produce identical, comparable data (§D). The Lab is itself deployed by Hop3 onto a Hop3 server — a real app in the catalog, and so also a platform probe.

## Detailed design

### A. Architecture and placement

```
 Hop3 server (the Lab host)                         Hetzner Cloud (ephemeral targets)
 ┌─────────────────────────────────────┐           ┌───────────────┐  ┌───────────────┐
 │  hop3-testlab (deployed by Hop3)    │  SSH/API  │  target #1    │  │  target #N    │
 │                                     │ ────────► │  fresh Hop3   │  │  fresh Hop3   │
 │  scheduler ─► runner(s) ─► engine   │           │  + deployed   │  │  + deployed   │
 │                  │(hop3-testing lib)│ ◄──────── │    apps       │  │    apps       │
 │                  ▼                  │  logs     └───────────────┘  └───────────────┘
 │   PostgreSQL  +  artifact store     │
 │                  ▲                  │
 │   web service ───┘  (dashboard/API  │
 └─────────────────────────────────────┘
```

The runner provisions a *pool* of targets (§F), deploys Hop3 to each, and drives the suite via the `DeploymentTarget` ABC. Provisioning credentials (Hetzner token, SSH keys) live in the Lab host's secret store. Targets are torn down at run end (cost control), unless `--keep` is set for debugging.

### B. Reuse of hop3-testing (library, not CLI text)

The reuse boundary is the functional core of `hop3-testing`, promoted to a stable internal API:

- `Orchestrator.run(plan) -> RunResult` — generalizes today's orchestrator to accept a *pool* of targets and a *shard* of the catalog, and to emit results incrementally (callback/queue) so the dashboard fills during the night.
- `collect_diagnostic_bundle(target, test) -> Bundle` — ADR 043's shared collector, the data source for §C. **This ADR depends on ADR 043's diagnostic bundle.**
- `Catalog.scan() -> [TestSpec]` — unchanged.
- `ResultStore` — extended with a read/query API and a Postgres backend (§ data model).

The CLI becomes a headless driver of the same `Orchestrator` writing to the same store (recording `target_type` and a `mode` of `cli` vs `nightly`). Library-over-CLI because the dashboard needs *structured* results and *bundle references*, not re-parsed console text — and sharing the engine guarantees the manual and scheduled paths can never diverge.

### C. Collecting all useful data — and surfacing it legibly

This is the heart of the product: ADR 043's bundle made first-class and browsable. For **every** test, pass or fail, the runner captures the bundle (build / app / nginx / journal / proxy-probe / deploy / http / dns / manifest) *before teardown*, since the logs vanish with the server. The lab-specific design rules make the data *useful*, not just present:

- **Always-collect, even on infra failure** — provisioning failed, target unreachable, run aborted: capture whatever exists (Hetzner console, partial transcript). A run that dies still leaves a breadcrumb.
- **Headline-first, drill-down on demand** — each test gets a ≤ ~12-line headline (a classifier: `proxy-502 / build-failure / addon-unreachable / app-crash / timeout`) plus the decisive lines; the full bundle is one click away (§E). This answers both "missing on remote" and "overwhelming when present."
- **Collision-safe, attributable** — bundles keyed by `(run_id, test_id)` (fixing the "two focalboard logs overwrite each other" bug), each addressable by URL.
- **Tail-bounded** — each section capped so the artifact store stays sane.
- **Redaction** — env vars/tokens scrubbed before storage/display (see Security).

### D. Coexisting with manual CLI runs

The failure mode to avoid is *two systems with two truths*. The single engine/store (§B) is what forces convergence:

- **One store.** Both `hop3-test cloud` and the scheduler write to the same Postgres store with the same schema and bundle format, so a manual run **shows up in the dashboard** automatically, tagged `mode=cli` and attributed to the operator.
- **Provenance.** Every run records who/what started it (`scheduled-nightly`, `cli:<user>`, `web:<user>`), git SHA, branch, target distro/image. Trends can filter to nightly-only so ad-hoc runs don't pollute the baseline.
- **Concurrency & isolation.** Each run owns its provisioned target(s); a lightweight lease prevents two runs from claiming the same server, and the nightly scheduler queues (or refuses) if a conflicting run holds the pool.
- **Re-run one from anywhere.** The web UI's "re-run this failed test" and `hop3-test cloud <app> --reuse` are the same single-test path; the result attaches to the original run as a retry, feeding flakiness detection (§E).
- **Local-repo parity.** The CLI's `--use-local-repo` is preserved; scheduled runs default to a branch/SHA. Both record exactly what was tested.

### E. The dashboard: status, drill-down, trends

Three server-rendered views (Litestar + HTMX, consistent with the hop3-server dashboard) with a light charting lib; `generate_html_report` is kept as a static export/fallback.

- **Morning dashboard** — overall green/red, per-suite rollup (apps / demos / tutorials / platform-e2e), total duration vs the 6 h budget, and the **diff vs the previous nightly**: newly-failing (surfaced first), newly-fixed, still-failing, and flaky.
- **Test page** — for one test: the headline classifier and status, the full bundle as tabs (build / app / nginx / journal / deploy / http / proxy-probe), the diff against its last passing run, its recent-history strip, and a "Re-run" button.
- **Trends** — pass-rate over time, per-app history ("focalboard started failing on 2026-05-30, commit abc123"), duration trends (early warning before the budget is breached), and flakiness ranking. These are the queries the new schema is built to serve.

### F. Finishing overnight — scaling the target pool

Serial real deploys of the full catalog will not fit 6 h on one server, and the deploy path is largely serial per server (concurrent deploys to one host interfere). The primary lever is **horizontal: a pool of Hetzner targets**, with the catalog **sharded** across them.

- **Sharded fan-out** — partition the catalog into N shards, one per target, run in parallel, merge results.
- **Duration-aware bin-packing** — balance shards from historical per-test durations so all targets finish near the same time.
- **Budget enforcement + autoscale** — the scheduler projects total wall-clock from history; if `projected > 6 h`, it provisions more targets or, as a logged last resort, sheds lowest-priority (P2) tests — **never silently**; what was dropped is recorded and shown.
- **Streaming results** — each test persists as it completes, so the dashboard is useful *during* the night and a late crash doesn't lose everything.
- **Caching** — reused base images per target (ADR 043's image-reuse fix) so provisioning isn't re-paid per shard.
- **Cost control** — ephemeral targets, torn down at run end; pool size is the cost/speed dial.

### Data model (extends `results/models.py`, moved to PostgreSQL)

- `TestRun` — add `trigger` (scheduled/cli/web + actor), `git_sha`, `pool_size`, `budget_seconds`, `projected_seconds`, `shed_tests`, per-phase timings.
- `TestResult` — add `status` (pass/fail/skip/error/flaky), `classification`, `duration`, `target`/`distro`/`image`/`shard`, `retry_of`, and `bundle_ref` — the field that makes failure history queryable and browsable. Index `(test_name, started_at)` and `(run_id, status)` for the trend/diff queries.
- A manifest per bundle describing each captured section, its size, and its storage location.

## Example

```
# Scheduled nightly (equivalent CLI form):
hop3-testlab run --suite all --pool 4 --branch main   # provision 4 targets, shard, run, collect, report

# A developer's manual run lands in the same dashboard:
hop3-test cloud focalboard --use-local-repo           # mode=cli, tagged cli:<user>

# Morning: dashboard shows "3 regressions". Click focalboard → headline: proxy_pass :8000 but app
#   LISTENing :8001 → nginx tab → "connect() failed (111) upstream 127.0.0.1:8000" → one-click "Re-run".
```

## Consequences

**Positive**

- Nightly failures become actionable by 9 a.m.: one screen, full logs, the silent-502 cause spelled out.
- One engine / one store means the CLI and web app can never diverge; manual runs enrich the same history.
- Trends turn the suite into a platform-health instrument (regressions, flakiness, duration creep) — serving the ethos.
- Dogfooding: the Lab is itself a real Hop3 app, and so a platform probe.
- The 6 h budget becomes a managed dial (pool size), not a hope.

**Negative / costs**

- A new subproject to build and maintain (web + scheduler + worker + schema + UI).
- Hard dependency on ADR 043's diagnostic bundle — the product is only as good as the bundle.
- Real money: provisioning N Hetzner servers nightly. Needs cost monitoring and teardown guarantees.
- Promoting `hop3-testing`'s internals to a stable API constrains future refactors there.
- Artifact storage grows; needs retention/pruning.

## Security implications

- The Lab holds **Hetzner tokens and SSH keys** — it can create and destroy servers. Scope tokens minimally; store in the host secret store; never in the DB or logs.
- **Logs may contain secrets** (app env vars, tokens). Redact before storage and display; treat the artifact store as sensitive.
- The dashboard exposes deployment internals → require authentication (reuse Hop3 auth / ADR 014); not public by default.
- Ephemeral targets must be reliably torn down even on crash (a leak is cost + exposure).

## Alternatives considered

- **Off-the-shelf CI as runner + reporter (GitHub Actions / GitLab / Woodpecker / SourceHut).** Generic CI gives logs and history but not the test-specific deployment diagnostics (the silent-502 probe, the per-app bundle, the apps-as-probe framing), nor easy orchestration of a scaled Hetzner pool, nor dogfooding. A hybrid (CI as executor, Lab as reporting/trends layer) is possible — noted as future work.
- **Static report only (pytest-html / Allure / `generate_html_report`).** No scheduling, trigger, trends, scaling, or live fill. Kept as an export, not the product.
- **Extend the hop3-server dashboard instead of a new app.** Rejected for now: keeps test infrastructure and Hetzner credentials out of the product server; the Lab has a different lifecycle and blast radius.
- **Shell out to and parse the `hop3-test` CLI.** Rejected: lossy and risks CLI/web divergence (§B/§D).

## Open questions / decisions

1. **Runner topology** — separate worker process / queue (arq), or in-process? Affects concurrency, crash isolation, and the manual/scheduled locking (§D). *(Open.)*
2. **DB** — PostgreSQL for the Lab; SQLite stays for the test fixtures.
3. **Artifact store** — pluggable; leaning on Advanced Alchemy's object-storage type.
4. **Pool size** — one server for v1; sharded pool later.
5. **Multi-provider** — Hetzner only now; pluggable later.
6. **Auth & exposure** — own credentials for v1; reuse Hop3 auth (ADR 014) later.
7. **Relationship to SourceHut** — SourceHut stays the per-distro PR/commit CI (ADR 043); the Lab owns the nightly full-suite surface.

## Future work

- Notifications (email/Matrix/…) on new regressions.
