# Hop3 Test Status

**Last updated:** 2026-09-14.

Where the suites stand today. The *structure* is [ADR 043](../adrs/043-unified-testing-architecture.md) and [`strategy.md`](strategy.md); the *commands* are [`cheat-sheet.md`](cheat-sheet.md) and the quick reference in `CLAUDE.md`. This file only records what currently passes, and every number on it is reproducible by the command beside it — if you are reading it more than a few weeks after the date above, re-run them rather than believe them.

## The layers

Three, decided by what a test *needs* (Docker, root, host mutation), not by how complex it is. `c_system/` and `d_e2e/` are gone: the first dissolved into the other two, the second was renamed `c_e2e/`.

| Layer | Directory | Docker | hop3-server | Command |
|-------|-----------|--------|------------|---------|
| Unit | `tests/a_unit/` | no | 3370 collected | `uv run pytest packages/hop3-server/tests/a_unit` |
| Integration | `tests/b_integration/` | no (in-process, in-memory DB) | 559 collected | `uv run pytest packages/hop3-server/tests/b_integration` |
| E2E | `tests/c_e2e/` | yes (real deploy) | 59 collected | `uv run pytest packages/hop3-server/tests/c_e2e` |

## Current results

| Suite | Result | Time | Command |
|-------|--------|------|---------|
| Fast tier, all packages | 5900 passed, 1 skipped | ~45 s | `make test-fast` |
| Integration, hop3-server | 537 passed, 22 skipped | ~42 s | `uv run pytest packages/hop3-server/tests/b_integration` |
| Docker e2e | green, no skips | ~15 min | `make test-e2e` |
| App catalog, remote target | **153 of 161** | 5 h 20 m | `hop3-test run --host <server> --with all` |

The integration skips are opt-in by design and each names a resource the harness does not provision: a live Garage node (`HOP3_TEST_GARAGE_ADMIN`), and the procfs-reading tests, which are Linux-only and skip on a developer's Mac.

The c_e2e layer reached **no skips** during the 0.7.3 gate, which is the bar it is held to — a skip whose reason is not a resource we cannot provision is a hole pretending to be coverage. Getting there found seven platform faults.

## The last full catalog run

2026-09-14 evening, 161 app tests against a remote target, 5 h 26 m. **159 passed, 2 failed** — up from 153 that morning and 153 two days before, with every one of the morning's eight causes addressed in between.

The two that remain are the same shape: a `contains` marker that names no page the app serves.

| Failure | What it serves | Fix |
|---------|----------------|-----|
| invoice-ninja-nix | `/` returns 200 with Laravel's react shell; the recipe asserted a 302 to `/setup`, which is what Invoice Ninja answers with *no* database | marker corrected to the native variant's |
| xwiki-nix | `/xwiki/bin/view/Main/` returns 302 to the distribution wizard, whose page is XWiki's own; the validation allowed only 200 and 202 | 302 added, the body assertion carries the proof |

Both were named by the deploy's own output rather than by reading the app, which is the change that made this run worth more than the last: the failure path now asks the app what it serves before it says anything about workers or timeouts. invoice-ninja-nix had been failing for two runs against a diagnosis that pointed at the wrong subsystem entirely.

### What the morning's eight cost, and what they bought

Five of the eight were the platform's fault, not the recipes'. Three could only have been found by a real application with an opinion of its own — one that refuses anonymous clients, one whose administrator sees a different page than its users, one whose package manager moved underneath it. None is reachable from a unit or e2e layer, which is the argument for running this at all.

## Known gaps

- **Two e2e sessions on one machine silently share a container.** The Docker target has a fixed name and fixed ports, so a second session tears the first's container down and re-installs under it, and neither is told. Recorded in [`../todo.md`](../todo.md) with a fix shape. Until it is fixed: one e2e session per machine, and a failure seen while another was running is not evidence.
- **The e2e image build fails intermittently on apt**, before any test runs. Seen once, under the two-session conditions above; re-confirm on a quiet machine before chasing it.
- **53 recipes assert nothing at start**, because their content assertion sits on a path the healthcheck does not probe. Tracked in [`../plans/plan-0.7.x.md`](../plans/plan-0.7.x.md) §4.
- **The trusted-HTTPS login path has never run end to end.** The Docker container has no admin domain and no trusted certificate, so the e2e proves the fallback half only.
