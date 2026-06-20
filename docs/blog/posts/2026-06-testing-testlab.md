---
date: 2026-06-19
template: blog_post.html
series: How Hop3 is Tested
series_order: 5
description: The nightly Test Lab — a Hop3-hosted web app that provisions cloud servers, runs the whole suite, and turns every failure into a queryable, trend-aware report.
tags:
  - Testing
  - Test Lab
  - Architecture
---

# The Test Lab: Making the Nightly Suite Legible

Running the whole test suite every night is only the first half of the job. The full matrix — real apps, demos, tutorials, platform e2e, across distros, on real cloud servers — produces a *mountain* of pass/fail data and diagnostic logs. If that data lands in a write-only file nobody can query, the suite is a tree falling in an empty forest. The point of testing is the *finding*, and a finding only counts if someone sees it the next morning.

So Hop3 has a dedicated application for exactly this: **`hop3-testlab`**, specified in [ADR 044](/adrs/044-nightly-test-lab/). It's the consumer that makes a nightly run *actionable* — green/red at a glance, every log for every failure one click away, trends over time, and a scheduler that gets it done before breakfast.

## Why a whole app for it

[ADR 043](/adrs/043-unified-testing-architecture/) did the hard part: it made the nightly data *exist and be uniform*, via the shared diagnostic bundle that every runner emits. But it left the data inert — a single-file SQLite store with no query API, a static report blind to trends, no scheduler, no way to browse a failed test's full logs, no flakiness view, no way to re-run from a UI. The Test Lab is the complement: [ADR 043](/adrs/043-unified-testing-architecture/) makes the data uniform; [ADR 044](/adrs/044-nightly-test-lab/) makes it *visible, queryable, and scheduled*.

It also lands squarely on the project ethos: *packaging apps is system-validation work; each app is a deliberate probe of the platform's edges.* The nightly suite is the instrument; the Test Lab is the readout that turns each failure into a visible platform backlog item.

## One engine, two front-ends

The cardinal rule that keeps the CLI and the dashboard from ever diverging: **the Test Lab does not shell out to the `hop3-test` CLI and parse its text.** It imports the [test runner](2026-06-testing-runner.md)'s functional core — the orchestrator, the `DeploymentTarget` abstraction, the catalog scanner, the shared `collect_diagnostic_bundle` — *as a library*, and writes structured results to a shared store.

The consequence is that the CLI and the web app are two thin shells over the **same** engine and the **same** store. A developer's manual `hop3-test cloud` run and a scheduled nightly run produce *identical, comparable* data — a manual run even shows up in the dashboard automatically, tagged with its provenance (`scheduled-nightly`, `cli:<user>`, `web:<user>`), git SHA, branch, and target distro. There is exactly one truth, and you can never accidentally build a second.

## The shape of it

```
 Hop3 server (the Lab host)                    Hetzner Cloud (ephemeral targets)
 ┌──────────────────────────────────┐          ┌────────────┐  ┌────────────┐
 │  hop3-testlab (deployed by Hop3)  │  SSH/API │ target #1  │  │ target #N  │
 │  scheduler ─► runner(s) ─► engine │ ───────► │ fresh Hop3 │  │ fresh Hop3 │
 │                  │ (hop3-testing) │ ◄─────── │ + apps     │  │ + apps     │
 │                  ▼                │  logs    └────────────┘  └────────────┘
 │  PostgreSQL  +  artifact store    │
 │                  ▲                │
 │  web service ────┘ (dashboard/API)│
 └──────────────────────────────────┘
```

| Component | Role | Stack |
|-----------|------|-------|
| **Web service** | dashboard + JSON API: browse runs, tests, logs, trends; trigger ad-hoc runs | Litestar + Advanced Alchemy + Dishka, server-rendered + HTMX |
| **Scheduler** | kicks off the nightly run on a timer; enforces the 6-hour budget | APScheduler / systemd timer |
| **Runner** | provision pool → deploy → run suites → collect bundles → persist → teardown | reuses `hop3-testing` as a library |
| **Datastore** | queryable results + trends | PostgreSQL |
| **Artifact store** | per-test diagnostic bundles | filesystem volume now, object storage later |

The same UI/stack as the hop3-server dashboard (Litestar + HTMX), so a single approach covers every Hop3 web surface.

## Dogfooded, and itself a probe

The Test Lab **runs on a Hop3 server and is deployed by Hop3** — it's a real app in the catalog. This goes beyond dogfooding: a Litestar + Postgres + background-scheduler app is a genuinely demanding workload, so deploying the Lab *is itself* a platform probe. The thing that reports on Hop3's failures is also one of the apps testing for them.

It then **remote-controls Hetzner**: the runner provisions a *pool* of ephemeral targets, deploys Hop3 to each, and shards the catalog across them. Targets are torn down at run end for cost control (unless `--keep` is set for debugging).

## Blank slate, every run

A nightly result is only trustworthy if it doesn't depend on what ran before it. So a Test Lab run starts from a genuine blank slate — for cloud targets, that means a full **OS rebuild of the throwaway server**, the Hop3 install included. This has sharp operational edges that are worth being explicit about, because a run that *silently* tests a dirty server is worse than no run at all:

- It needs a registered SSH key and a **dedicated, disposable** server to rebuild — the rebuild **wipes the entire box**, so it must never point at anything you care about.
- If it can't reach a true blank slate, it **aborts loudly**, refusing to run against leftover state. (A silent "SKIPPED" against a dirty server is the cardinal sin the whole testing rework was meant to kill.)
- Trigger logs land in `~/.hop3/testlab-logs/` so a run that dies during provisioning still leaves a breadcrumb.

This takes the *non-reproducibility* failure mode seriously: a result that depends on what ran before it is worthless.

## What you see in the morning

Three server-rendered views turn the mountain of data into a glance:

- **Morning dashboard** — overall green/red, a per-suite rollup (apps / demos / tutorials / platform-e2e), total duration against the 6-hour budget, and — the most valuable thing — the **diff against the previous nightly**: newly-failing (surfaced first), newly-fixed, still-failing, and flaky. The headline is *what changed*; the 70 individual results are a click away.
- **Test page** — for one test: the headline classifier (`proxy-502 / build-failure / addon-unreachable / app-crash / timeout`), the full diagnostic bundle as tabs (build / app / nginx / journal / deploy / http / **proxy-probe**), the diff against its last passing run, a recent-history strip, and a one-click **re-run**.
- **Trends** — pass-rate over time, per-app history ("focalboard started failing on 2026-05-30, commit `abc123`"), duration trends (early warning before the 6-hour budget is breached), and a flakiness ranking.

Every bundle is keyed by `(run_id, test_id)` — so two apps' logs can never overwrite each other — addressable by URL, tail-bounded so the artifact store stays sane, and redacted (env vars and tokens scrubbed) before storage.

## Finishing overnight

The hard constraint is **under six hours**, reliably. Serial real deploys of the whole catalog won't fit on one server, and the deploy path is largely serial *per* server (concurrent deploys to one host interfere). So the primary lever is horizontal: a **pool** of Hetzner targets with the catalog **sharded** across them, scaling out until the wall-clock fits the budget. Duration trends exist precisely to warn before the budget is breached.

## Driving it

The Lab is operated through a small CLI alongside its web UI:

```bash
hop3-testlab serve          # the dashboard + API (add --reload in dev)
hop3-testlab schedule       # the nightly scheduler, in the foreground
hop3-testlab run --target hetzner --trigger manual --mode nightly   # a run now
hop3-testlab run --target hetzner --apps <path>                     # one app
hop3-testlab prune          # apply the build-log retention policy
```

A manual `run` writes to the same store as the scheduler, so it shows up in the same dashboard — the single-truth principle, all the way down.

## Where it sits

The Test Lab is the apex of the pyramid in [the testing overview](2026-06-how-hop3-is-tested.md): the **nightly** tier given a home. Below it, the [test runner](2026-06-testing-runner.md) provides the engine, the [demos](2026-06-testing-demos.md) and [validoc tutorials](2026-06-testing-validoc.md) provide much of the catalog, and the shared diagnostic bundle from [ADR 043](/adrs/043-unified-testing-architecture/) provides the data. The Lab's job is to make sure that, every morning, the night's findings are impossible to miss — and that each one reads, correctly, as a platform backlog item.

---

*The final part of a five-part series on [how Hop3 is tested](2026-06-how-hop3-is-tested.md). The full design is [ADR 044: Nightly Test Lab](/adrs/044-nightly-test-lab/), which builds on [ADR 043: Unified Testing Architecture](/adrs/043-unified-testing-architecture/).*
