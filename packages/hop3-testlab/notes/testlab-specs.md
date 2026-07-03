# Hop3 Test Lab (`hop3-testlab`) — Technical Specification (as-built)

**Status:** v0.2 (2026-06-18) — *rewritten to match the implementation* · **Implements:** [ADR 044](../../notes/adrs/044-nightly-test-lab.md) · **Depends on:** [ADR 043](../../notes/adrs/043-unified-testing-architecture.md) Phase 1 (the diagnostic bundle) · **Type:** subproject spec

This document now describes **what is actually built** in `packages/hop3-testlab/` (and the `hop3-testing` engine it drives), cited by path/symbol, with a clearly-marked **Deferred / not yet built** list per area. The v0.1 draft (2026-06-06) was a pre-implementation design; where the implementation diverged from that design, this version follows the code, and the original design intent is kept only as rationale or as a deferred item.

**One-paragraph summary of the shipped v1.** `hop3-testlab` is a Litestar + Dishka web app (Granian factory) over the **shared `hop3-testing` result store**. An APScheduler cron fires a nightly run (the dashboard is read-only; runs are also started via the CLI `run` command). Either way the **worker** (`worker.run_once`) takes a single-target **run lease**, blank-slate-rebuilds the Hetzner box (full-suite runs only), and spawns `hop3-test system …` as a killable subprocess; the engine writes results/bundles to the store as today. The web app reads that store and renders a morning dashboard, a live "running" panel (HTMX polling), per-run / per-build detail, browsable diagnostic bundles, trends, and mode profiles, behind session-cookie auth + CSRF. v1 is deliberately small (single Hetzner target, SQLite, in-process scheduler); the larger ADR-044 ambitions (Advanced-Alchemy schema, `Artifact`/`StoredObject`, incremental `on_result` writer, `HetznerPool` + sharding, redaction, SSE) are **not built** and are tracked as gaps below.

---

## 1. Guiding constraints (unchanged intent)

1. **Mirror hop3-server's stack** — Litestar + Dishka + SQLAlchemy (sync) + Jinja/HTMX/Alpine/Tailwind + Granian. The Test Lab is itself a Hop3 app (dogfooded). **Built.**
2. **One engine, one store** (ADR 044 §B/§D) — the CLI (`hop3-test run`) and the Test Lab read/write the *same* `hop3-testing` result store; the Lab never parses CLI text. **Built** for the read path; the dashboard is read-only and the run path is the nightly scheduler / CLI `run` driving the worker. The *write* path is still the engine's existing stateful `ResultStore.save()` (the incremental `on_result` writer is deferred, §7).
3. **Follow the playbook** — `litestar-dishka/{COMMON-GOTCHAS,CHECKLISTS}.md`. **Built** (Dishka `@inject`+`FromDishka`, `LitestarProvider`, generator session, APP/REQUEST scopes).
4. **v1 scope is deliberately small** — a *single* Hetzner (or Docker) target, the Lab's own credentials, in-process scheduling, SQLite. **Built as such.** The seams for pool/sharding/Postgres are *partially* present (config fields, lease epoch timestamps) but those features are not implemented.

---

## 2. Stack & conventions (as-built)

| Layer | Choice | Notes |
|-------|--------|-------|
| Web | `litestar[standard]>=2.22` | server-rendered templates + HTMX |
| DI | `dishka>=1.3` | `setup_dishka(create_async_container(...), app)`; `LitestarProvider()` present |
| ORM | `advanced-alchemy>=0.21` + `sqlalchemy~=2.0` (sync) | declared dep; the **shared store models are still plain `DeclarativeBase`** (§6), AA base classes not yet adopted |
| Migrations | **none / hand-rolled** | `create_all()` + `_ensure_columns()` `ALTER TABLE` in `hop3-testing/results/store.py`; **no Alembic** (§13) |
| DB | **SQLite** (`~/.hop3/test-results.db`, WAL) | `TestlabConfig.DATABASE_URI` exists for Postgres but is not exercised |
| Server | Granian (factory) | `target="hop3_testlab.web.asgi:create_app", factory=True` (`cli.py:_serve`) |
| Templates | Jinja + HTMX + Alpine + Tailwind (CDN) | `web/templates/base.html` |
| Scheduler | **APScheduler** in-process (`scheduler.py`) | `BackgroundScheduler` embedded in the web process; `BlockingScheduler` via `hop3-testlab schedule` |

**Sync SQLAlchemy.** As designed — the Lab reads the same sync `hop3-testing` store, so the session is a plain `sqlalchemy.orm.Session` (`db.py:get_session_factory`). The Dishka container is async (`make_async_container`) but yields a sync `Session`. No `asyncpg`.

**Session access in controllers: Dishka injection (`@inject` + `FromDishka[...]`) — built** (`web/controllers/*`, `di/providers.py`). Controllers stay thin and never touch a `Session` directly.

---

## 3. Mandatory best practices (from the playbooks)

The acceptance checklist is unchanged from the v0.1 draft and is honoured by the implementation: APP/REQUEST Dishka scopes; `@inject` on every handler using `FromDishka`; `LitestarProvider()` in the container; generator providers for the session; tuple `order_by`; `flush()` not `commit()` in tests + `refresh()` after flush + `get_one_or_none()` for delete checks; service session via `self.repository.session`; thin singleton controllers with explicit return annotations; state-over-behavior tests. See `litestar-dishka/COMMON-GOTCHAS.md` + `CHECKLISTS.md` for the verbatim rules.

---

## 4. Package layout (as-built)

`src/`-layout, workspace package `packages/hop3-testlab/`, entry point `hop3-testlab = "hop3_testlab.cli:main"`. The implementation uses **flat modules** (not the `scheduler/`, `worker/`, `trends/` sub-packages the draft proposed):

```
packages/hop3-testlab/
├── pyproject.toml                 # deps as §2; [project.scripts] hop3-testlab = hop3_testlab.cli:main
├── src/hop3_testlab/
│   ├── cli.py                     # serve | run | config | prune | schedule
│   ├── config.py                  # TestlabConfig singleton (env-driven)
│   ├── cloud_config.py            # TOML+env cloud creds / schedule / retention (~/.hop3/testlab/config.toml)
│   ├── db.py                      # get_session_factory() — SQLite engine (WAL, busy_timeout, check_same_thread=False)
│   ├── worker.py                  # run_once() subprocess engine driver + lease + blank-slate + stop control
│   ├── scheduler.py               # APScheduler nightly cron (Background + Blocking)
│   ├── leasing.py                 # single-target run lease over the RunLease row
│   ├── repositories.py            # RunsRepository (read side over the shared store)
│   ├── trends.py                  # diff_results / suite_rollup / predict_progress (ETA) / flakiness
│   ├── reports.py                 # build_run_report_md() — narrative markdown export
│   ├── catalog.py                 # cached Catalog + title_map()
│   ├── discriminators.py          # variant_of / type_of / short_app (test-name classification)
│   ├── bundles.py                 # read_bundle_sections() — read filesystem bundle dirs
│   ├── di/{container,providers}.py
│   └── web/
│       ├── asgi.py                # create_app() factory
│       ├── guards.py              # auth_guard
│       ├── controllers/           # dashboard, runs, running, builds, bundle, trends, profiles, auth (+ health)
│       └── templates/             # base.html + auth/ dashboard/ runs/ running/ builds/ bundle/ trends/ profiles/
└── tests/a_unit/                  # ~20 unit suites (auth, csrf, worker, scheduler, leasing, blank_slate, trends, …)
```

**The shared data + engine layer lives in `hop3-testing`** (`results/`, `system_tests/`, `bundle.py`, `catalog/`, `targets/`). `hop3-testlab` depends on `hop3-testing`. There is **no `alembic/`** in either package (§13).

---

## 5. Reuse boundary — what is actually shared vs still pending

ADR 044 §B's reuse boundary is the `hop3-testing` functional core. Current state of each piece:

### Imported / consumed as-is (built)
- `targets/base.py` `DeploymentTarget` ABC and the Docker/SSH targets — driven by the engine the worker spawns.
- `catalog/scanner.py` `Catalog` + `catalog/models.py` `TestDefinition` — wrapped by `hop3_testlab/catalog.py` (cached, with `title_map`).
- `bundle.py` `collect_diagnostic_bundle` + `bundle_ids.py` — the engine writes bundle dirs under `~/.hop3/test-runs/<run_id>/`; the Lab reads them via `bundles.read_bundle_sections` (§12).
- `results/store.py` `ResultStore` + `results/models.py` — the shared schema the engine writes and the Lab reads (§6).

### ADR-044 substrate gaps — **still open** (the "one engine, one store" hardening is partial)
- **G1 — Pool provisioning/teardown: NOT BUILT.** `system_tests/hetzner.py::HetznerManager` still only `rebuild`/`reboot`s ONE pre-existing `server_id`; there is no `HetznerPool`/`create_server`/`delete_server`. `system_tests/multi_distro.py` is still subprocess fan-out.
- **G2 — `Orchestrator.run(pool, shard, on_result)`: NOT BUILT.** There is no in-process incremental orchestrator; the old `system_tests/orchestrator.py::DailyTestOrchestrator` was single-target, `rich.Console`-coupled, and emitted only at end-of-run — it was removed (ADR 052 7b.7, folded into `hop3-test run --provider`). The Lab does not call any such thing directly — it shells `hop3-test run` (§10).
- **G3 — Bundle-on-every-test + redaction: PARTIAL / NOT BUILT.** Bundles are collected on **failure** paths (`runners/deployment.py:493 if not passed`), not uniformly on every passing test; there is **no secret redaction** anywhere (§12).
- **G4 — Postgres + real migrations + engine abstraction: NOT BUILT.** SQLite only, `create_all` + hand-rolled `_ensure_columns` (§13).
- **G5 — Advanced-Alchemy base + `Artifact` model: NOT BUILT.** Models are plain `DeclarativeBase`/Integer PKs; there is no `Artifact` row and no `StoredObject` (§6).
- **G7 — Run-id-parameterized incremental writer: NOT BUILT.** `ResultStore.save()` is still stateful (`self._current_run`); the engine owns the write, the Lab only reads (§7).

### Built in `hop3-testlab` (the product shell)
- **G8/G10** Web service (dashboard + detail + trends + bundle viewer), §9.
- **G9** APScheduler + per-run subprocess worker + run lease + blank-slate, §10/§11.
- **G11** Auth/CSRF + lease-based exposure, §11/§14.

---

## 6. Data model (as-built)

The shared schema lives in `hop3-testing/results/models.py` and is **not yet migrated** to Advanced-Alchemy. It is a plain `class Base(DeclarativeBase)` with `Integer` PKs. There is **no `Artifact` model and no `StoredObject`** — diagnostic bundles are stored on the filesystem and referenced by id/path columns. Tables (note the actual names):

- **`test_runs`** (`TestRun`): `id` (int PK), `started_at`, `finished_at`, `run_uid` (indexed), `mode`, `target_type`, `target_name`, `hop3_version`, `total_tests`, `passed_tests`, `failed_tests`, `trigger`, `actor`, `git_sha`, `pool_size`, `budget_seconds`, `projected_seconds`, `phase_timings` (JSON), `shed_tests` (JSON), `run_metadata` (JSON), `planned_counts` (JSON). `run_uid` uniqueness is enforced via a partial unique index (`store.py:_ensure_columns`), not a column constraint.
- **`test_results`** (`TestResultRecord`): `id` (int PK), `run_id` (FK→`test_runs`), `test_name`, `category`, `tier`, `priority`, `passed` (bool), `status`, `classification`, `headline` (Text — the ≤12-line summary the dashboard/`why` render with no blob read), `duration`, `error`, `logs`, `bundle_run_id`, `bundle_path` (Text — absolute path to the on-disk bundle dir), `target`, `distro`, `image`, `shard`, `retry_of` (FK→`test_results`, re-run lineage), `phase_timings` (JSON), `executed_at`.
- **`validation_results`** (`ValidationRecord`): per-validation rows for a result.
- **`run_lease`** (`RunLease`, §11): `id`, `target_id` (unique, indexed), `holder`, `run_uid`, `acquired_at`, `expires_at` (epoch float — works on both backends), `pid`, `pid_starttime`.
- **`build_log`** (`BuildLog`): compressed per-phase build/deploy logs — `phase`, `algo`, `data` (blob), `size`; read back decompressed by `RunsRepository.build_logs` for the build-detail view.

**Bundles on the filesystem, not in the DB.** A diagnostic bundle is a directory `~/.hop3/test-runs/<run_id>/<section>.txt` written by the engine; `TestResultRecord.bundle_run_id` + `bundle_path` point at it. This is the actual implementation of ADR 044 OQ#4 today — **not** the `StoredObject`/`Artifact`-row design the v0.1 draft proposed.

### Deferred (was the v0.1 design for §6)
- Migrate to `BigIntAuditBase`; per-bundle-section `Artifact` rows keyed by `(result_id, section)`; `StoredObject` blob backend (filesystem → object-store by config); ADR-044 composite indexes as first-class. None of this is built.

---

## 7. Persistence & query layer (as-built)

- **Write side: the engine's existing `ResultStore` (`hop3-testing/results/store.py`).** Still stateful (`self._current_run`), one run at a time, written by the spawned `hop3-test system` subprocess. The run-id-parameterized incremental `on_result` writer (G7) is **not built** — and is not needed for v1's single-target, single-writer model.
- **Read side: `hop3_testlab/repositories.py::RunsRepository`** over the shared store (plain session, not `SQLAlchemySyncRepository`). Methods actually present: `list_recent`, `get(run_uid)`, `results_for(run)` (failed-first), `progress_by_type(run)`, `previous_run(run)`, `active_run`, `recent_completed(mode, target_type)`, `abort_active`, `sweep_orphans`, `target_busy`, `get_result`, `build_logs(result_id)`, `pass_fail_history(limit_runs)`, `current_lease`/`release_lease`.
- **Analysis: `hop3_testlab/trends.py`** — pure functions over fetched rows: `diff_results(current, previous)` → regressions / fixed / still-failing / not-run; `suite_rollup(results)` → per-category counts; `predict_progress(...)` → live ETA from history; flakiness from `pass_fail_history`. `reports.py::build_run_report_md` renders a narrative markdown summary; `discriminators.py` classifies a test name into variant (docker/nix/native/template) and type (app/demo/tutorial).

### Deferred
- A first-class trends *service* with `history(test_name)`, `duration_trend`, `pass_rate_over_time` as indexed DB queries (today some are pure functions over recent rows; `duration_trend` is absent). Concurrency-safe parameterized writes (G7).

---

## 8. Dependency injection (as-built — `di/`)

Three providers (`di/providers.py`), scopes per the playbook, wired in `di/container.py` via `make_async_container(ConfigProvider(), DatabaseProvider(), RepositoryProvider(), LitestarProvider())` and `setup_dishka(...)` in `web/asgi.py:create_app`:

- `ConfigProvider` — `Scope.APP` — `config() -> TestlabConfig` (`TestlabConfig.get_instance()`).
- `DatabaseProvider` — `Scope.REQUEST` — generator `session(config) -> Iterator[Session]` (commit on success, rollback on exception, close in `finally`), over `db.get_session_factory()`.
- `RepositoryProvider` — `Scope.REQUEST` — `runs(session) -> RunsRepository`.

`LitestarProvider()` is present (required for `Request` injection). The container is closed on shutdown.

---

## 9. Web service (as-built — Litestar + HTMX)

`web/asgi.py:create_app()` builds the Litestar app: Dishka wiring, `ServerSideSessionConfig` (in-memory store), `CSRFConfig` (active unless `TESTLAB_UNSAFE`), a `NotAuthorizedException` → `/auth/login` redirect handler, and the APScheduler startup/shutdown hooks (§10). Controllers mirror hop3-server conventions (`path`, `guards=[auth_guard]`, `@get/@post`, `sync_to_thread=False`) and **inject** deps with `@inject` + `FromDishka[...]`.

**Routes actually implemented:**

| Controller | Path | Routes |
|------------|------|--------|
| `HealthController` | `/health` | `GET /` (public liveness) |
| `AuthController` | `/auth` | `GET /login`, `POST /login`, `GET /logout` |
| `DashboardController` | `/` | `GET /` — morning dashboard |
| `RunsController` | `/runs` | `GET /{run_uid}`, `GET /{run_uid}/report.md` |
| `RunningController` | `/running` | `GET /` (live panel), `POST /stop` |
| `BuildController` | `/builds` | `GET /{result_id}` — per-phase build logs |
| `BundleController` | `/bundle` | `GET /{bundle_run_id}` — browse bundle sections |
| `TrendsController` | `/trends` | `GET /` |
| `ProfilesController` | `/profiles` | `GET /`, `POST /save`, `POST /reset`, `POST /delete` |

**Views (built):** morning dashboard (overall + per-suite rollup + diff-vs-previous + schedule/flash status); run detail (results table failed-first, diff, markdown report export); the **running** panel; build detail; bundle viewer (sections from disk); trends (pass/fail history + flakiness); and **mode profiles** (save/reset/delete named run configs — an addition not in the v0.1 draft).

**HTMX patterns (built):** the running panel auto-refreshes via `hx-get` polling (~5s) — `RunningController` + `running/_panel.html`. The dashboard is read-only; runs are started by the nightly scheduler or the CLI `run` command driving the worker (§10), not by a web POST. Templates: `base.html` (CDN htmx/alpine/tailwind) + per-view dirs.

### Deferred
- **SSE live-fill** (the draft's `Stream(text/event-stream)` during the night) — not built; the running panel polls instead.
- **Bearer-token JSON API** — not built (session-cookie only; ADR 044 OQ#7 left this for later).
- A per-test **Re-run** button — not surfaced (the engine path exists via `hop3-test system --reuse`).

---

## 10. Scheduler & worker (as-built)

**Scheduler (`scheduler.py`).** APScheduler in-process. `build_background_scheduler()` registers a `CronTrigger(hour, minute)` nightly job (`add_nightly_job`, id `"nightly"`); `web/asgi.py` starts it on app startup when `load_schedule().enabled` and stores it on `app.state`, shutting it down gracefully. `hop3-testlab schedule` runs a `BlockingScheduler` (`run_blocking`) for a standalone scheduler process — it registers the dispatcher too, so a standalone scheduler runs what it enqueues. The nightly job **enqueues** the configured `[schedule].profile` (a `BuildRequest` with `actor="nightly"`); the dispatcher then runs it on a free pool server — the same single path as the UI's Start build. Idle **loudly** when no profile is configured.

**Worker (`worker.py::run_once(target_id, *, trigger, mode, spec, executor)`).** The single entry point for queued/dispatcher builds and the CLI `run`:
1. `leasing.try_acquire(...)` — returns `False` (no run) if the target is busy (§11).
2. `RunsRepository.sweep_orphans()` — clears crashed/unfinished runs.
3. For a full-suite **Hetzner** run, `_rebuild_blank_slate(cfg)` — OS rebuild + SSH wait; **aborts loudly** if the SSH key can't be resolved or SSH never comes ready. Per-app re-runs and Docker targets skip the rebuild. `run_blockers(...)` does this validation **pre-flight** so a doomed run is refused before spawn (no fake "started").
4. `_default_executor` spawns the engine as a killable subprocess (`subprocess.Popen(..., start_new_session=True)`): `hop3-test system --docker --with all …` or `--ssh --host <ip> --with all …`, with `--mode <mode>` (full suite) or `--apps <path>` (single), passing `HOP3_TEST_TRIGGER`/`HOP3_TEST_SSH_KEY`/`HOP3_TEST_META` env.
5. `_record_engine_pid` stores the PID + `/proc` starttime on the lease for reuse-proof stop control; `terminate_engine(pid, starttime)` SIGTERMs the process group then SIGKILLs after a grace period.
6. The lease is released in a `finally`.

**Pre-flight (built).** Before any spawn, `run_blockers(...)` validates the run (SSH key resolvable, box reachable) and **refuses** a doomed run rather than reporting "started" (no fake success). The dashboard's manual run-trigger (the old `RunsController.trigger` / `POST /runs/trigger` and its `~/.hop3/testlab-logs/trigger-*.log` breadcrumb) was **removed in v2**: runs now start via a Profile → "Start build" (enqueue a `BuildRequest`) → the dispatcher picks a free pool server and drives the worker, tagging the run `build-<id>`.

### Deferred
- 6h wall-clock **budget enforcement** beyond the lease TTL; **arq** promotion; multi-shard fan-out.

---

## 11. Concurrency, the run lease, and the budget (as-built)

**Run lease (`leasing.py` over the `run_lease` row).** One row per `target_id`. `try_acquire(session, target_id, holder, run_uid, ttl_seconds=6*3600)` is non-blocking: it claims the row unless a live (unexpired) lease exists, in which case it returns `False` and the caller refuses (the dashboard shows `?run=busy`). `expires_at` is an **epoch float** (works on SQLite and Postgres), so an abandoned lease is reclaimable after TTL. `set_pid`/`current_lease`/`is_held`/`force_release`/`release` round out the API; the PID + starttime power the dashboard **Stop** control. This is the SQLite/row implementation; the Postgres `pg_try_advisory_lock` variant is **not built** (and not needed at single-target).

**Provenance & convergence (built).** `trigger`/`actor`/`mode`/`git_sha` are recorded on `TestRun`, so a CLI `hop3-test` run, a dispatcher build, *and* a nightly all appear in the dashboard: the run's `trigger` is `cli` or `build-<id>` (queued build), and a queued build's origin is on the `BuildRequest.actor` (`web` | `nightly`). `retry_of` links a re-run to its origin for flakiness.

### Deferred
- Postgres advisory-lock lease; duration-aware **bin-packing** / budget projection; **shedding** lowest-priority tests under budget (the `TestRun.shed_tests` / `budget_seconds` / `projected_seconds` columns exist as seams but nothing populates a shed list).

---

## 12. Diagnostic bundles & artifacts (as-built — the heart, §C)

The engine's `collect_diagnostic_bundle(target, app, …)` (`hop3-testing/bundle.py`) runs **before teardown** on failure paths and writes a bundle directory `~/.hop3/test-runs/<run_id>/` with one `<section>.txt` per section (`proxy_probe`, `nginx`, `app`, `journal`, `build`, `deploy`, `http`, `dns`, `manifest`). The classifier produces a `headline` stored as a `Text` column on `test_results` (dashboard + `hop3-test why` render it with no file read). The Lab's `bundles.read_bundle_sections(dir)` reads the present sections in order; `BundleController` renders them as a browsable page; `BuildController` shows the decompressed `build_log` phases.

### Deferred (was the v0.1 §12 design)
- **Collect on every test** (today: failure-focused, not uniformly on passes).
- **Secret redaction** of section text before storage/display — **not implemented anywhere** (open security item; ADR 044 Security).
- **`Artifact` rows + `StoredObject`** keyed by `(result_id, section)` — today bundles are filesystem dirs referenced by `bundle_path`, so two same-named sections across results don't collide (separate dirs), but they are not individually addressable DB rows.

---

## 13. Migrations & dual-backend (as-built)

**No Alembic.** The shared store schema is created by `ResultStore` via `Base.metadata.create_all()` plus a hand-rolled `_ensure_columns()` that issues additive `ALTER TABLE … ADD COLUMN` and creates the trend/filter indexes + the `run_uid` partial-unique index (`hop3-testing/results/store.py`). `hop3_testlab/db.py` opens the SQLite engine with WAL, `busy_timeout`, `foreign_keys=ON`, `check_same_thread=False`, and ensures the schema on first use. `hop3-testlab prune` trims old `build_log` rows.

### Deferred (was the v0.1 §13 design)
- Bundled `alembic.ini` + `alembic/env.py`, `db:upgrade` gate, unstamped-DB adoption, `BigIntAuditBase.metadata` target, `script.py.mako` AA-type aliases, and an exercised **Postgres** backend. `TestlabConfig.DATABASE_URI` exists but the SQLite path is the only one used today.

---

## 14. Auth & security (as-built)

- **Auth: session-cookie + CSRF, single admin credential.** `web/guards.py:auth_guard` allows the request when `TESTLAB_UNSAFE` is set (dev/tests) or `request.session["user_id"]` is present, else raises `NotAuthorizedException` → `/auth/login`. `AuthController` compares the password with `secrets.compare_digest` against `TestlabConfig.USERNAME`/`PASSWORD` and sets the session. CSRF uses `TestlabConfig.SECRET_KEY` (explicit, or derived stably from the password). `/health` and `/auth/login` are public. **Bearer-token auth is not built** (OQ#7 deferred).
- **Cloud secrets** (`cloud_config.py`): Hetzner API token + SSH key live in `~/.hop3/testlab/config.toml` (gitignored, `$VAR` expansion) or env (`HETZNER_API_TOKEN`, `HOP3_TEST_SSH_KEY`) — `[hetzner]` (`api_token`, `server_id`, `image`, `ssh_key_name`), `[ssh]` (`key_path`), `[schedule]`, `[retention]`. Never in the DB; `hop3-testlab config` masks the token.
- **Teardown / blank-slate** — full-suite Hetzner runs rebuild the OS up-front (`_rebuild_blank_slate`), and the pre-flight `run_blockers` refuses the run if the SSH key can't be re-injected (so we never run dirty or spawn a doomed run).

### Deferred
- Bundle/display **secret redaction** (§12); ephemeral-server orphan reaping (no ephemeral provisioning yet, §5 G1); bearer API.

---

## 15. Testing (as-built)

`packages/hop3-testlab/tests/a_unit/` holds ~20 unit suites covering the shipped surface: `test_auth`, `test_csrf`, `test_worker`, `test_scheduler`, `test_leasing`, `test_blank_slate`, `test_trends`/`test_trends_page`, `test_run_detail`/`test_run_report`, `test_build_detail`, `test_bundles`, `test_running`, `test_progress_by_type`, `test_discriminators`, `test_catalog`, `test_cloud_config`, `test_profiles_page`, `test_app_smoke`. Controllers are exercised via `litestar.testing` with `TESTLAB_UNSAFE` toggled to test both the guard and the authenticated paths; the lease/worker/blank-slate logic is tested with stubbed executors and a Hetzner manager double.

**Layering (updated).** The suites are now classified per ADR 043 by *what a test needs*: `tests/a_unit/` holds the pure suites (`discriminators`, `trends`, `cloud_config`, `catalog`, `blank_slate`) stamped `fast`; the ~16 suites that drive a real SQLite store / the real Litestar app / real git live in `tests/b_integration/` (stamped `integration`). As a thin orchestration shell the Lab is legitimately integration-heavy.

### Deferred
- `c_e2e` (a real provision→deploy→collect→teardown, `needs_docker`) is still empty — it lands with the slice-1 compose-run acceptance test (see `tasks/todo.md`). A dual-backend (SQLite vs Postgres) lease test (only the SQLite path exists).

---

## 16. Status vs the phased build plan

| Phase | Intent | Status |
|-------|--------|--------|
| **M0** Schema + store (AA + `Artifact` + `StoredObject`) | migrate models, add artifact rows | **Not done** — store still plain `DeclarativeBase`/Integer PKs, filesystem bundles, hand-rolled `_ensure_columns` (§6/§13) |
| **M1** Query API + parameterized writer | incremental `on_result`, trends service | **Partial** — read repos + trend functions built (§7); incremental writer (G7) not done |
| **M2** Bundle everywhere + artifacts + redaction | collect on pass, redact, `Artifact` rows | **Partial** — failure-bundles + headline + viewer built; every-test + redaction + artifact rows not done (§12) |
| **M3** Web service (read-only) | factory + DI + auth + views | **Done** — dashboard / run / build / bundle / trends / profiles, session auth + CSRF (§8/§9/§14) |
| **M4** Scheduler + worker + lease (single target) | APScheduler → subprocess, lease, blank-slate | **Done** — incl. pre-flight `run_blockers` + stop control + blank-slate (§10/§11) |
| **M5** Re-run + trends polish + retention | re-run button, flakiness, retention | **Partial** — flakiness + markdown report + `prune` built; per-test Re-run button + retention job not done |
| **M6+** Pool + sharding + budget autoscale + arq | additive scale-out | **Not started** (G1/G2, §5) |

**Net:** the *product shell* (M3/M4) is built and tested; the *engine/store hardening* (M0–M2 substrate: AA schema, artifacts, redaction, parameterized writer) and *scale-out* (M6) are the open work.

---

## 17. Open questions (status vs ADR 044)

| # | ADR 044 question | Current state |
|---|------------------|---------------|
| 1 | Runner topology (arq?) | **APScheduler + per-run subprocess** — built; arq deferred. |
| 3 | DB | **SQLite** in practice; Postgres config seam exists, unused/untested. |
| 4 | Artifact store | **Filesystem bundle dirs** (`~/.hop3/test-runs/<run_id>/`); `StoredObject`/`Artifact` rows deferred. |
| 5 | Pool model | **Single target** (one rebuilt Hetzner box or Docker); `HetznerPool`/sharding not built. |
| 6 | Multi-provider | Hetzner-only via `HetznerManager`. |
| 7 | Auth & exposure | **Lab's own credentials**, session-cookie + CSRF, not public by default; bearer deferred (§14). |
| 8 | Relationship to SourceHut | Unchanged: SourceHut = per-distro PR/commit CI; the Lab = nightly full-suite. |

**Still genuinely open (and now load-bearing for the advertised-set gate):** bundle **secret redaction** (no denylist/allowlist yet — the single most important security gap); the AA-schema / `Artifact` / Alembic migration (M0); incremental persistence + budget shedding; the charting approach for trends; the retention window.
