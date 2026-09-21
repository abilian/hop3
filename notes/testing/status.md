# Hop3 Test Status

**Last updated:** 2026-09-18.

The *structure* is [ADR 043](../adrs/043-unified-testing-architecture.md) and [`strategy.md`](strategy.md); the *commands* are [`cheat-sheet.md`](cheat-sheet.md) and the quick reference in `CLAUDE.md`. This file records where the suites stand today, and nothing more. Every number on it is reproducible by the command beside it. If you are reading it more than a few weeks after the date above, re-run the commands before trusting the numbers.

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
| App catalog, remote target | 161 of 161, **inputs changed mid-run** | 5 h 27 m | `hop3-test run --host <server> --with all` |

The integration skips are opt-in by design and each names a resource the harness does not provision: a live Garage node (`HOP3_TEST_GARAGE_ADMIN`), and the procfs-reading tests, which are Linux-only and skip on a developer's Mac.

The c_e2e layer reached **no skips** during the 0.7.3 gate, which is the bar it is held to. A skip whose reason is not a resource we cannot provision is a hole pretending to be coverage. Getting there found seven platform faults.

## The last full catalog run

**The 2026-09-16 run returned 161 of 161, and it is not a gate.** It started 18:34 and finished 00:01, and the php-fpm migration was committed into the sibling catalog checkout at 20:19 — the tree the harness scans. Ten PHP recipes were deployed after that point, from migrated recipes, against a server that did not yet carry the fixes those recipes need. They passed. Either the migrated recipes work on an unfixed server, which nothing has measured, or the run read a mixture of old and new recipes; the run cannot tell us which. A result taken while its own inputs were being edited is not evidence, the same way a failure seen alongside another session is not evidence.

What still stands from it: the six platform fixes of 2026-09-14/15 were in place for the whole run, and 153 → 159 → 161 across three runs tracks real repair. What does not stand is "the catalog passes", because nobody can say which catalog.

**The gate is still owed**: one run, start to finish, against a tree that does not change under it.

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

- **A warm Nix store hides an app that cannot build.** `directus-nixgen` passed nine runs between 2026-08-24 and 2026-09-16 and failed on 2026-09-21 with `reused 0, downloaded 1267`: its dependency-fetch derivation was rebuilt for the first time since August, and `pnpm fetch` died compiling `isolated-vm@5.0.3`. Nix short-circuits a fixed-output derivation whose path already exists, so neither the catalog run nor `hop3-tools nix check-reproducible` re-enters that step once it has succeeded once. Every nix-gen app has the same hiding place.
- **The catalog run is the only layer that exercises php-fpm against real applications**, and the last full run predates it. Fourteen PHP recipes moved onto the php-fpm runtime on 2026-09-16 and were each checked one at a time on Docker; they have not been through a full run together. The two platform fixtures that cover the runtime cheaply are `apps/test-apps-procfile/060-php-hello` and `070-php-public`.
- **A feature can ship with a green suite and never have run.** php-fpm shipped on 2026-09-11 with seven defects the suite could not see, because every recipe's own `[run].start` overrode the new worker and the tests asserted the shape of a command string rather than that a pool came up. Any new code path behind a precedence rule has zero users on the day it ships; its fixture has to exist before it does.

- **Two e2e sessions on one machine silently share a container.** The Docker target has a fixed name and fixed ports, so a second session tears the first's container down and re-installs under it, and neither is told. Recorded in [`../todo.md`](../todo.md) with a fix shape. Until it is fixed: one e2e session per machine. A failure seen while another session was running carries no weight.
- **The e2e image build fails intermittently on apt**, before any test runs. Seen once, under the two-session conditions above; re-confirm on a quiet machine before chasing it.
- **53 recipes assert nothing at start**, because their content assertion sits on a path the healthcheck does not probe. Tracked in [`../plans/plan-0.7.x.md`](../plans/plan-0.7.x.md) §4.
- **The trusted-HTTPS login path has never run end to end.** The Docker container has no admin domain and no trusted certificate, so the e2e validates the fallback path only.
