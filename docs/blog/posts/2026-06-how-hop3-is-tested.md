---
date: 2026-06-19
template: blog_post.html
series: How Hop3 is Tested
series_order: 1
description: "A map of how Hop3 tests itself: three runners, three layers, four speed tiers, and why each one exists."
tags:
  - Testing
  - Architecture
  - Engineering
---

# How Hop3 is Tested

Hop3 is a Platform-as-a-Service: its whole job is to take someone else's application and *make it run*: build it, wire up a database, put it behind a reverse proxy with TLS, keep it alive. That makes testing unusually hard. A unit test can tell you a function returns the right value; it cannot tell you that a freshly-deployed Flask app is actually reachable over HTTPS, or that nginx is pointing at the port the app is really listening on.

So Hop3 is tested at every level, from pure functions up to real applications deployed onto real servers. Four companion posts go deep on each piece.

## The philosophy: packaging apps is system-validation work

Hop3's testing strategy follows from a single conviction, baked into the project's ethos:

> Every app we package is a deliberate probe of the platform's edges. Each real-world application exposes something the toy fixtures can't — a missing toolchain, an addon that doesn't wire up, an opaque error path, a proxy that points at the wrong port.

This reframes testing as a continuous experiment against the platform's boundaries. Each deployment probes an edge; a failed one is a *finding*: usually a platform backlog item, occasionally a business-reasons decision to drop the app. The most valuable test is the one that surfaces a gap we didn't know we had.

That conviction produced the testing architecture described in [ADR 043: Unified Testing Architecture](/developers/adrs/043-unified-testing-architecture/), which this post summarises.

## Three runners, three domains

Hop3 deliberately keeps **three** test runners, each owning a crisp, non-overlapping domain:

| Runner | Tests… | Notes |
|--------|--------|-------|
| **pytest** | the **platform code**: unit → integration → e2e | the inner-loop tool; the only runner that produces coverage |
| **hop3-test** | **applications** (real apps + demos): deploy + verify | exercises the platform indirectly; owns the app catalog |
| **validoc** | **narratives**: tutorials-as-tests, long CLI-driven scenarios | literate, doc-shaped; verifies the docs match reality |

The "unification" is three things: a memorable map of *which runner for what*, **one** set of speed tiers shared across all three, and **one** shared diagnostic bundle that every runner emits whenever a real server is involved.

Each runner gets its own post:

- **[The Demos](2026-06-testing-demos.md):** small, scripted, educational deployments that are also tests.
- **[Testable Docs with validoc](2026-06-testing-validoc.md):** tutorials whose code blocks are executed and asserted.
- **[The Test Runner (hop3-test)](2026-06-testing-runner.md):** why we built it, and the one deploy-and-verify path it owns.
- **[The Test Lab](2026-06-testing-testlab.md):** the nightly web app that runs the whole suite against real cloud servers and reports on it.

## The pytest pyramid: three layers and one placement rule

For the platform code itself, pytest is organised into three directory layers:

| Layer | Contains | Docker / root / host-mutation? | Counts toward coverage? |
|-------|----------|-------------------------------|------------------------|
| `a_unit` | pure functions and classes, no real I/O | no | ✅ yes |
| `b_integration` | multi-component, real DB/subprocess, **but hermetic** | no | ✅ yes |
| `c_e2e` | deploys / real-server tests | **yes** | ❌ no (out-of-process) |

The crux is the **placement rule**: a test's home is decided by one question: **does it need Docker, root, a real server, or host mutation?** Complexity is irrelevant to where it lands.

- Pure logic → `a_unit`.
- Heavyweight but hermetic: runs in a `tmp_path`, a temp/in-memory DB, a monkeypatched `HOME`, no privileged ops, cleans up after itself → `b_integration`.
- Needs Docker / root / a real server / `/etc` → `c_e2e`.

This deliberately pushes work *down* the pyramid: prefer `b_integration` whenever a test can run hermetically. It also produces a happy alignment with coverage: the two *fast* layers (`a_unit`, `b_integration`) are exactly the two that *move the coverage number*, because `c_e2e` runs in a separate process or container where `coverage.py` can't see it.

(This supersedes [ADR 026](/developers/adrs/026-dashboard-ui-test-classification/), which had classified tests by a real-vs-mocked-dependency axis. The Docker/root/host-mutation axis is the better boundary, and was itself enabled by the testability work in [ADR 027](/developers/adrs/027-config-system-refactoring/).)

## Four speed tiers

A test's *layer* says what it needs; a test's *tier* says how fast the feedback is. The tiers are stamped onto tests automatically from their directory by an autouse pytest hook, so selection just works:

| Tier | Scope | Docker? | When |
|------|-------|---------|------|
| **fast** | `a_unit` (+ the fastest `b_integration`) | no | every save / pre-commit |
| **check** | the full pytest pyramid incl. `c_e2e` + lint + types | yes | pre-push / PR |
| **apps** | `hop3-test`: a P0 subset, or one named app | yes | when touching deployer/proxy/builders |
| **nightly** | full `hop3-test` matrix + `validoc` + multi-distro, **HTML report** | yes | cron / release |

A few deliberate choices fall out of this:

- **The inner loop is under a minute.** `make test-fast` runs `pytest -m fast` and stays entirely in-process.
- **Bare `pytest` never spins up Docker.** The default `testpaths` is the in-process layers only; CI invokes the Docker `c_e2e` layer explicitly. (This fixed the single loudest day-to-day complaint: a reflexive `pytest` used to trigger a multi-minute image build.)
- **The slow platform guarantees gate every push.** Backups, git-push, and the proxy tests live in **check**, because they're core guarantees a release rests on.

## One deploy-and-verify path

The original sin that [ADR 043](/developers/adrs/043-unified-testing-architecture/) set out to fix was that *deploy-and-verify was implemented four times over*: the test runner, the pytest Docker fixtures, the demos, and a tutorial script each stood up a server and verified an app independently. Now everything that stands up a server routes through one primitive: the `DeploymentTarget` abstraction over the real `hop3-deploy` command:

| Target | When | Gate |
|--------|------|------|
| `--docker` | default; dev + CI | the only one wired into routine CI |
| `--host …` | systemd-specific paths (rootd, nginx reload) Docker can't fully exercise | nightly / manual |
| Hetzner Cloud | multi-distro, real-server release validation | release gate |

One primitive means one place to fix a bug, and one consistent set of diagnostics on failure.

## The silent-502: diagnosis as a first-class feature

The review that produced [ADR 043](/developers/adrs/043-unified-testing-architecture/) was triggered by a specific, infuriating production failure: **a healthy app behind a 502, with no useful diagnostic anywhere.** The app was up and answering on its port; nginx was pointing at the *wrong* port; and no test surface captured it.

So Hop3 treats diagnosis as a first-class feature. Every runner that touches a real server emits the *same* diagnostic bundle on failure, before teardown (because the logs vanish with the server):

- A **proxy probe**: `curl 127.0.0.1:<port>`, the actual `LISTEN` port from `ss -ltnp`, the nginx `proxy_pass` target, and the **diff** between them. This is the silent-502 fix.
- nginx error/access logs, app/uwsgi logs, the journal, the build transcript, the deploy transcript, the HTTP exchange, DNS.

Each section is tail-bounded (rich on disk, terse on screen), and a classifier turns the bundle into a one-line verdict: `proxy-502 / build-failure / addon-unreachable / app-crash / timeout`, with `hop3-test why <run-id>` to drill into any section.

## Where CI runs

The CI of record is SourceHut (`.builds/`). The GitHub Actions workflows were vestigial and have been removed. `nox` survives as the multi-Python driver (3.11–3.14). Docker distros run the `check` tier; non-Docker distros run `fast`.

## The nightly Test Lab

The top of the pyramid (the full suite against real cloud servers, every night) is run and reported by a dedicated web application, **hop3-testlab** ([ADR 044](/developers/adrs/044-nightly-test-lab/)). It provisions a pool of ephemeral Hetzner servers, deploys Hop3 to each, shards the catalog across them, collects a diagnostic bundle for every test (pass or fail), tears the servers down, and serves a dashboard with trends, flakiness ranking, and a diff against the previous night. It reuses the test runner *as a library*, so a manual CLI run and a scheduled nightly run produce identical, comparable data. The [Test Lab post](2026-06-testing-testlab.md) covers it in depth.

## The shape of it

Put together:

```
fast      pytest a_unit (+fast b_integration)         < 1 min, every save
check     pytest full pyramid + lint + types          pre-push / PR
apps      hop3-test (real apps + demos), Docker        touching deploy paths
nightly   hop3-test + validoc, multi-distro, Hetzner   cron, via the Test Lab
```

Three runners for three domains, three layers placed by what they *need*, four tiers named by how fast they answer, one deploy path, one diagnostic bundle. A PaaS that can't prove an app is actually reachable over HTTPS has no business calling itself one.

---

*This is the overview of a five-part series on how Hop3 tests itself: [the demos](2026-06-testing-demos.md), [testable docs (validoc)](2026-06-testing-validoc.md), [the test runner](2026-06-testing-runner.md), and [the nightly Test Lab](2026-06-testing-testlab.md). The full rationale lives in [ADR 043: Unified Testing Architecture](/developers/adrs/043-unified-testing-architecture/).*
