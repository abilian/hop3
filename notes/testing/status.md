# Hop3 Test Status

**Last updated:** 2026-10-05.

The *structure* is [ADR 043](../adrs/043-unified-testing-architecture.md) and [`strategy.md`](strategy.md); the *commands* are [`cheat-sheet.md`](cheat-sheet.md) and the quick reference in `CLAUDE.md`. This file records where the suites stand today, and nothing more. Every number on it is reproducible by the command beside it. If you are reading it more than a few weeks after the date above, re-run the commands before trusting the numbers.

**Reading a run since 2026-10-05.** Four changes in how a run decides:

- A server deploy that carried past a ⚠ fails the run, unless the warning is on `TOLERATED_DEPLOY_WARNINGS` with its reason (`notes/installer-fail-loud-audit.md`).
- The server is installed with what the selected apps declare: their addons and the runtime their builder needs (`nix`, `docker`). Nothing is installed by default.
- On the Docker target, Docker-built apps are left out before the deploy, each named: the container cannot run Docker. Most `-docker` recipes declare no test targets, so a Docker-target run now lists them as skipped; they run against a server with `--host`.
- A run that includes an app declaring email selects the `catch` backend, and the mail lands in Mailpit (`190-flask-email` checks the path).

## The layers

Three, decided by what a test *needs* (Docker, root, host mutation). Complexity plays no part in the decision. `c_system/` and `d_e2e/` are gone: the first dissolved into the other two, the second was renamed `c_e2e/`.

| Layer | Directory | Docker | hop3-server | Command |
|-------|-----------|--------|------------|---------|
| Unit | `tests/a_unit/` | no | 3422 collected | `uv run pytest packages/hop3-server/tests/a_unit` |
| Integration | `tests/b_integration/` | no (in-process, in-memory DB) | 559 collected | `uv run pytest packages/hop3-server/tests/b_integration` |
| E2E | `tests/c_e2e/` | yes (real deploy) | 59 collected | `uv run pytest packages/hop3-server/tests/c_e2e` |

## Current results

| Suite | Result | Time | Command |
|-------|--------|------|---------|
| Fast tier, all packages | 5983 passed, 1 skipped | ~55 s | `make test-fast` |
| Integration, hop3-server | 537 passed, 22 skipped | ~42 s | `uv run pytest packages/hop3-server/tests/b_integration` |
| Docker e2e | green, no skips | ~15 min | `make test-e2e` |
| App catalog, remote target | **162 of 162**, over three runs | ~5 h | `hop3-test run --host <server> --with all` |

The integration skips are opt-in by design and each names a resource the harness does not provision: a live Garage node (`HOP3_TEST_GARAGE_ADMIN`), and the procfs-reading tests, which are Linux-only and skip on a developer's Mac.

The c_e2e layer reached **no skips** during the 0.7.3 gate, which is the bar it is held to. A skip whose reason is not a resource we cannot provision is a hole pretending to be coverage. Getting there found seven platform faults.

## The last full catalog run

**2026-09-21, against 0.7.5's tree, in three parts.** The first run of the catalog that gates anything: one server build, one committed tree, nobody editing underneath it.

| Run | Scope | Result | Time |
|-----|-------|--------|------|
| 1174 | alpha, **cold Nix store** (`--provider hetzner`), `--from local` | 108 / 108 | 4 h 00 m |
| 1176 | golden + beta | 52 / 54 | 1 h 05 m |
| 1177 | the two failures, re-checked alone | 2 / 2 | 4 m |

**All ten migrated PHP recipes passed** — bookstack, dolibarr, easy-appointments, invoice-ninja, kanboard, limesurvey, matomo, nextcloud, paheko, wordpress — the first run of them against the php-fpm fixes. **Thirty Nix apps built on an empty store**, which had not happened since August and is what blocker #38 exists to keep happening.

Both failures in run 1176 were outside the platform, and both passed on re-run:

| Failure | Cause |
|---------|-------|
| uptime-kuma | GitHub answered `504 Gateway Time-out` six times for the release tarball; `hop3-fetch` backed off 2/4/8/16/32s and failed with the URL and the status |
| bugsink-nix | gunicorn bound its port, no worker booted, nothing logged; a `hop3-test` run had been interrupted on that box two minutes before |

Two apps passed on a re-run rather than in the sweep. Neither is a code defect and neither reproduced, but a gate that needed a retry has a retry in it.

### The run before this one, and why it was not a gate

### The run before it, and how its two failures were found

2026-09-14 evening, 161 app tests, 5 h 26 m. **159 passed, 2 failed.** The two were the same shape: a `contains` marker that names no page the app serves.

| Failure | What it serves | Fix |
|---------|----------------|-----|
| invoice-ninja-nix | `/` returns 200 with Laravel's react shell; the recipe asserted a 302 to `/setup`, which is what Invoice Ninja answers with *no* database | marker corrected to the native variant's |
| xwiki-nix | `/xwiki/bin/view/Main/` returns 302 to the distribution wizard, whose page is XWiki's own; the validation allowed only 200 and 202 | 302 added, the body assertion carries the proof |

Both were named by the deploy's own output. Reading the app would have missed them. That change made the run catch what the previous two had missed: the failure path now asks the app what it serves before it says anything about workers or timeouts. invoice-ninja-nix had been failing for two runs against a diagnosis that pointed at the wrong subsystem entirely.

### What the morning's eight cost, and what they bought

Five of the eight were the platform's fault. Three could only have been found by a real application with an opinion of its own: one that refuses anonymous clients, one whose administrator sees a different page than its users, one whose package manager moved underneath it. None is reachable from a unit or e2e layer, which is the argument for running this at all.

## Known gaps

- **A warm Nix store hides an app that cannot build.** `directus-nixgen` passed nine runs between 2026-08-24 and 2026-09-16 and failed on 2026-09-21 with `reused 0, downloaded 1267`: its dependency-fetch derivation was rebuilt for the first time since August, and `pnpm fetch` died compiling `isolated-vm@5.0.3`. Nix short-circuits a fixed-output derivation whose path already exists, so neither the catalog run nor `hop3-tools nix check-reproducible` re-enters that step once it has succeeded once. Every nix-gen app has the same hiding place. `make test-nix-cold` is the answer: `--clean` removes Hop3 and leaves `/nix`, so only an OS rebuild empties the store. Run it on a schedule, because a warm store makes the cheap gates say nothing.
- **The two php-fpm platform fixtures are the cheap check**, and the catalog run is the only layer that exercises the runtime against real applications. `apps/test-apps-procfile/060-php-hello` and `070-php-public` cover it in seconds; the fourteen migrated recipes went through a full run on 2026-09-21.
- **A feature can ship with a green suite and never have run.** php-fpm shipped on 2026-09-11 with seven defects the suite could not see, because every recipe's own `[run].start` overrode the new worker and the tests asserted the shape of a command string rather than that a pool came up. Any new code path behind a precedence rule has zero users on the day it ships; its fixture has to exist before it does.

- **Two e2e sessions on one machine silently share a container.** The Docker target has a fixed name and fixed ports, so a second session tears the first's container down and re-installs under it, and neither is told. Recorded in [`../todo.md`](../todo.md) with a fix shape. Until it is fixed: one e2e session per machine. A failure seen while another session was running carries no weight.
- **The e2e image build fails intermittently on apt**, before any test runs. Seen once, under the two-session conditions above; re-confirm on a quiet machine before chasing it.
- **53 recipes assert nothing at start**, because their content assertion sits on a path the healthcheck does not probe. Tracked in [`../plans/plan-0.7.x.md`](../plans/plan-0.7.x.md) §4.
- **The trusted-HTTPS login path has never run end to end.** The Docker container has no admin domain and no trusted certificate, so the e2e validates the fallback path only.
