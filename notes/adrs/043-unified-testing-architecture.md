# ADR 043: Unified Testing Architecture

- **Status**: Accepted
- **Type**: Process
- **Created**: 2026-06-05
- **Supersedes**: [ADR 026](./026-dashboard-ui-test-classification.md) (Dashboard UI Test Classification)
- **Related-ADRs**: [004](./004-development-tooling.md) (development-tooling), [027](./027-config-system-refactoring.md) (config-system-refactoring-for-testability), [030](./030-two-level-build-architecture.md) (two-level-build-architecture), [041](./041-privileged-operations-agent.md) (privileged-operations-agent)
- **Related-notes**: `notes/security/rootd-hardening.md`, `docs/src/dev/testing-strategy.md`

## Context

### The problems

The project accumulated several parallel testing approaches, each added for a good local reason, with no unifying model. A contributor must hold a large set of entry points across many layers in their head: and know *which still work*, because a sizeable fraction are dead. An audit of the full surface (pytest layers, the `hop3-test` runner, the standalone `demos/` harness, the tutorial scripts, `validoc`, `nox`, the Makefile/CI) found:

1. **No fast daily path, and the defaults are slow.** `c_system` sits in the default `testpaths`, so bare `uv run pytest` *and* `make test` pull the Docker layer and can trigger a multi-minute image build. The fast unit suite is reachable only by hand-typing its directory. The loudest day-to-day complaint.
2. **The primary GitHub CI workflow is dead.** `ci.yml` (the broadest trigger: every push and PR) runs `nox` sessions that do not exist; it fails at session selection on every run. The CI of record is **SourceHut** (`.builds/`); GitHub Actions is unused.
3. **`hop3-test` advertises commands it doesn't register.** Only `system`, `list`, `cloud` exist; `dev / apps / ci / nightly / hetzner / multi-distro / show` error out: yet the README, `CLAUDE.md`, and the Makefile call them, so several Makefile targets are broken.
4. **Deploy-and-verify is implemented four times over the same path.** `hop3-test system`, the pytest Docker fixtures, `demos/demo.py` + `demos/lib`, and `scripts/run-all-tutorials.py` each stand up a server and verify an app independently: over the one real `hop3-deploy` primitive that `hop3-testing`'s `DeploymentTarget` ABC already wraps.
5. **Diagnostics are forked, with inverted coverage.** The richest collector (journalctl, nginx error/access, docker daemon) is wired *only* to the Hetzner path; the everyday Docker run gets the leanest bundle; the pytest Docker layers collect **nothing** on failure. No surface has a proxy-reachability probe: so the most common production failure, a healthy app behind a front-end 502 because nginx points at the wrong port/host (the "silent-502" class), is captured by *none*.
6. **The pyramid has collapsed in practice.** `c_system` no longer pulls its weight: its only live tests are one fully-skipped module and one in-process `TestClient` + in-memory-DB test (which belongs in `b_integration`). Every test embodying the original "CLI ↔ server in a container, no deploys" intent is disabled. The real boundary today is `b_integration` (in-process, fast) vs `d_e2e` (Docker, real deploy).
7. **Three incompatible speed taxonomies, none meaningful in practice.** Directory layers, decorative pytest markers, and `hop3-test`'s `P0/P1/P2` + tier labels. `pytest -m "not slow"` cannot select a fast lane because the markers aren't applied.
8. **Whole packages run in no CI.** `hop3-installer`, `hop3-rootd` (security-sensitive: [ADR 041](./041-privileged-operations-agent.md) and the v0.6 hardening note), `hop3-tui`, and `hop3-testing` appear in no Makefile target and no workflow.

### The parts that must survive

- The `DeploymentTarget` ABC (`hop3-testing/targets/`) is a clean abstraction over docker/ssh/hetzner: the right single deploy-and-verify primitive.
- `validoc` is a literate-test substrate: tutorials are Markdown with executable, asserted code blocks. It can drive *any* CLI scenario.
- An HTML report generator already exists (`diagnostics.py::generate_html_report`): the nightly artifact we want.
- `nox` is alive as SourceHut's multi-Python driver; only the GitHub workflow that referenced non-existent sessions is dead.

### Why now

Pre-1.0, with license to make breaking changes. The cost of carrying a broken, fast-loop-less, diagnosis-less testing surface into 1.0 is far higher than consolidating now. The consolidation is mostly clarification and deletion; the one new component is a shared diagnostic bundle.

## Decision

### 1. Three runners, three domains

We keep **three** runners, each with a crisp, non-overlapping domain; we do **not** collapse them into one binary, and pytest stays a first-class, directly-invokable runner.

| Runner | Tests… | Notes |
|--------|--------|-------|
| **pytest** | the **platform code** (unit → integration → e2e) | the inner-loop tool; the only runner that produces coverage |
| **hop3-test** | **applications** (real apps + demos): deploy + verify | exercises the platform indirectly; owns the app catalog + the `DeploymentTarget` ABC |
| **validoc** | **narratives**: tutorials-as-tests, long CLI-driven scenarios | literate, doc-shaped; verifies docs match reality |

The "unification" is: (a) a memorable map of *which runner for what*, (b) one set of speed tiers across all three, and (c) **one shared diagnostic bundle** every runner calls whenever a deployed server is involved.

### 2. The pytest pyramid: three layers + a placement rule

`c_system` **dissolves**, and `d_e2e` is **renamed `c_e2e`**:

| Layer | Contains | Docker / root / host-mutation? | Counts toward coverage? |
|-------|----------|-------------------------------|------------------------|
| `a_unit` | pure functions/classes, no real I/O | no | ✅ yes |
| `b_integration` | multi-component, real DB/subprocess, **but hermetic** | no | ✅ yes |
| `c_e2e` | deploys / real-server tests | **yes** | ❌ no (out-of-process) |

**The placement rule (the crux).** The axis is **"does this test need Docker, root, a real server, or host mutation?"** The test's complexity is not what decides it. Pure logic → `a_unit`. Heavyweight but hermetic (runs in `tmp_path`, temp/in-memory DB, monkeypatched `HOME`, no privileged ops, no `/etc`, cleans up after itself) → `b_integration`. Needs Docker / root / a real server / system mutation → `c_e2e`. This deliberately pushes work *down*: prefer `b_integration` whenever a test can run hermetically.

**Duplication across layers is allowed and expected.** A hermetic backup-logic test in `b_integration` and a real-deploy backup test in `c_e2e` test different things and should coexist; the only question is which layer a test's *dependencies* place it in.

This **supersedes [ADR 026](./026-dashboard-ui-test-classification.md)**, which classified dashboard tests by the real-vs-mocked-dependency axis. Under the Docker/root/host-mutation axis, a test running real `App.create()` against `tmp_path` with an in-memory DB is *hermetic* and belongs in `b_integration`: reversing [ADR 026](./026-dashboard-ui-test-classification.md). The one in-process `c_system` test moves there; the skipped Postgres-backup test is made hermetic or moved to `c_e2e`; the disabled proxy tests are revived into `c_e2e` (they exercise the silent-502 class).

### 3. Coverage policy

Coverage is measured on `a_unit` + `b_integration` only: the in-process layers `coverage.py` can see. `c_e2e` runs in a separate process/container and is pass/fail. This produces a happy alignment: the two *fast* layers are exactly the two that *move the coverage number*, so the placement rule both tightens the feedback loop and raises coverage.

### 4. The speed-tier ladder

Tiers are named by feedback latency and selected by pytest markers stamped from the directory layer by an autouse conftest hook: so the markers become real with zero per-test edits and stop depending on the broken directory pyramid.

| Tier | Scope | Docker? | Dev moment | CI |
|------|-------|---------|------------|----|
| **fast** | `a_unit` (+ fastest `b_integration`) | no | every save / pre-commit | non-Docker distros (Rocky, NixOS) |
| **check** | full pytest pyramid incl. `c_e2e` (backups, git-push, proxy) + lint + types | yes | pre-push / PR | Docker distros (Ubuntu) |
| **apps** | `hop3-test`: a P0 subset, or one named app | yes | touching deployer/proxy/builders | on-demand |
| **nightly** | full `hop3-test` app/demo matrix + `validoc` tutorials + multi-distro, **HTML report** | yes | cron / release | SourceHut nightly |

The slow Docker platform tests (backups, git-push, proxy) live in **`check`** and are not nightly-only (they are core guarantees and should gate a push). `check` requires Docker, so non-Docker distros run `fast` instead, matching the `.builds/` split. Bare `pytest` (and `make test`) run the in-process layers only (`a_unit` + `b_integration`); the `testpaths` default excludes the Docker `c_e2e` layer, so a reflexive `pytest` never spins up Docker; CI invokes `c_e2e` explicitly.

### 5. Unified entry points

The Makefile targets collapse to a small, all-working set:

| Target | Runs |
|--------|------|
| `make test-fast` | `pytest -m fast` (a_unit + fast integration), < 1 min |
| `make test` | the `check` tier |
| `make lint` / `make check` | ruff + reuse + deptry + pyrefly + mypy |
| `make test-cov` | `a_unit` + `b_integration` with `--cov` |
| `make test-apps` / `make test-app APP=…` | `hop3-test system` over a subset / one app |
| `uv run hop3-test system --docker --mode nightly` | `hop3-test` full matrix + demos + `validoc`, HTML report |

All dead targets are removed, and `hop3-test`'s advertised-but-unregistered commands are dropped from the docs.

### 6. One deploy-and-verify path

Everything that stands up a server routes through the `DeploymentTarget` ABC + the real `hop3-deploy` primitive: `hop3-test` (already does), the pytest `c_e2e` fixtures (today own a parallel Docker lifecycle), the demos, and `validoc`.

| Target | When | Gate |
|--------|------|------|
| `--docker` | default; dev + CI | the only one wired into routine CI |
| `--ssh-host <host>` | systemd-specific paths (rootd, nginx reload, www-data perms) Docker can't fully exercise | nightly / manual |
| `--provider hetzner` | multi-distro, real-server release validation | release gate only, behind `HETZNER_API_TOKEN` |

A developer can run one real e2e fast: `hop3-test system --docker <app>` against the cached image, with `--reuse` to iterate on verification alone. **Bug to fix in passing:** `c_e2e` rebuilds the Docker image every session while `c_system` checks-then-reuses it; the reuse behaviour becomes the shared default.

**Target selection is explicit, and Docker is the only default (a target env var is taboo for pytest).** A pytest run touches a remote box **only** when `--ssh-host <host>` is passed on the command line; with no flag it runs against Docker. The remote-host env vars `HOP3_TEST_HOST` and `HOP3_DEV_HOST` (and the alias `HOP3_TEST_SERVER`) are **never** read to select or point a pytest target: the root `conftest.py` strips them for the whole session. This closes a real defect: those vars, which a developer legitimately sets for `hop3-deploy-server` / `hop3-test`, used to make `pytest` deploy to that box, so an ordinary local test run collided with a live `hop3-test` run against the same server and corrupted its results. Selection by ambient state is the class of bug the [ADR 042](./042-cli-context-model.md) resolver was built to prevent; the test harness gets the same rule. (`HOP3_SSH_USER` is not a target selector, it only supplies the user for a `--ssh-host` value that omits `user@`, and is left readable.)

### 7. Shared diagnostics: the silent-502 fix

Replace the forked collectors with **one** shared contract, always invoked on failure, before cleanup:

```python
collect_diagnostic_bundle(target: DeploymentTarget, app: str) -> Bundle
```

Called from a single `try/finally` in the deploy-verify loop **and** from a pytest `c_e2e` fixture finalizer, so every failure (docker, ssh, hetzner, in-test) collects the same bundle. It uses only `target.exec_run`, retiring the current remote-exec mechanisms. Three layers ensure logs are never missing and never overwhelming:

1. **Headline** (always, ≤ ~12 lines): a classifier verdict (`proxy-502 / build-failure / addon-unreachable / app-crash / timeout`) plus the decisive signals.
2. **Drill-down** (on demand): `hop3-test why <run-id> --section nginx|journal|build|http|deploy|app` replays one section from the saved bundle. Nothing is dumped inline by default.
3. **Artifact** (always written): `~/.hop3/test-runs/<ISO>-<app>-<shortid>/`, recorded in one result store that keeps the bundle path so failure history is queryable. CI uploads it.

**Bundle manifest** (the union of today's richest collector, made target-agnostic):

- `proxy_probe.txt`: **the silent-502 fix, absent today:** `curl 127.0.0.1:<port>`, `ss -ltnp` for the actual LISTEN port, the nginx `proxy_pass` target, and the diff between them.
- `nginx.txt`: `error.log` + `access.log` tail + the rendered conf (today only the static conf is dumped).
- `app.txt`: app/uwsgi/granian/docker logs + listen check.
- `journal.txt`: `journalctl` (ssh/hetzner; container logs on docker).
- `build.txt`, `deploy.txt`, `http.txt`, `dns.txt`, `manifest.json`.

Each section is tail-bounded: rich on disk, terse on screen. `generate_html_report` renders these bundles as the nightly HTML report.

### 8. CI: GitHub vestigial, SourceHut real

- **GitHub Actions** (`ci.yml`, `test.yml`, `e2e.yml`) are vestigial and all three are removed; SourceHut is the sole CI.
- **SourceHut** `.builds/` is the CI of record (Ubuntu, Rocky, NixOS) and is itself partly broken. Fix: Docker distros run `check` once; the `nox` multi-Python fan-out runs the **fast** tier only; non-Docker distros run `fast`.
- **Keep `nox`** as the multi-Python driver. Its `pytest` session inherits the `testpaths` fix, so once `c_e2e` leaves the default path `nox` stops dragging Docker across Pythons. The redundant per-package fan-out can be dropped.

### 9. What gets deleted / absorbed

After a parity window (see migration):

- `.github/workflows/ci.yml` (dead).
- `scripts/run-all-tutorials.py` (and the never-existed `.sh`): tutorials become `validoc` runs driven by `hop3-test`.
- Orphaned `hop3-testing` code: `runners/validations.py::_validate_validoc` (a no-op that masks failures) and the redundant result DB.
- The forked diagnostics collectors, folded into `collect_diagnostic_bundle`.
- The dead Makefile targets (§5).

**Kept:** `demos/demo.py`, `demos/lib`, and `runners/demo.py`. A demo is simultaneously an educational walkthrough, a live demonstration, and a test, so a broken demo is a first-class regression. The meta runner exercises each demo in place (`DemoTestRunner` → `demos/demo.py`) and surfaces a non-zero exit as a failed test; `runners/demo.py` is the integration layer. The HTML generator, the catalog/scanner, the `targets/` ABC, the Hetzner orchestrator, and `runners/tutorial.py` (now reached via tutorial discovery) are also kept. The demo engine and its educational and demonstration roles are kept. Reducing demo/runner duplication within that constraint is welcome.

### 10. Cross-version upgrade validation

The e2e surface validates that a running server *upgrades* across releases without losing its schema or its ability to serve. It also validates that a version deploys. `hop3-test upgrade-chain` installs a baseline release on a fresh box, then walks a chain of versions (a git ref per hop, e.g. `0.6.2 → … → local`), performing an in-place update at each hop and asserting the server comes back healthy and the schema is readable.

Two properties make it a faithful upgrade test and keep it from becoming a self-test:

- **Each version is installed by its own installer.** A hop is a git ref; the chain checks it out into a worktree and runs *that* checkout's `hop3-deploy-server` (`uv run … --local`). Installing an old version with the *current* installer tests a pairing that never shipped: old binaries under a newer, stricter installer that rejects states an older, looser installer produced. The stable `--local`/`--git`/`--pypi` source flags (which every release accepts, and the current deployer keeps as aliases) let one harness drive any version's deployer.
- **The box is fresh.** The chain starts from a clean slate (a fresh Docker container or a rebuilt cloud VPS (`--provider hetzner`)) because an old release expects the toolchain/OS state of its era, and an existing server carries state that can mask a migration bug.

It reuses the one deploy primitive (§6): a hop is `target.start()` (baseline) or `target.redeploy()` (in-place upgrade) over the `DeploymentTarget` ABC, with the per-hop assertions running through `target.exec_run`. It belongs to the **nightly** tier (real deploys, minutes per hop) and the chain is data, so widening coverage is adding a version to the list. A release whose installed binaries can't even start (e.g. a broken older wheel) is not a viable baseline and is simply excluded from the chain; that exclusion is itself a finding.

## Migration plan

Strictly incremental; each phase ships value alone and is reversible. Ordered by leverage-per-hour.

> **Known constraint:** `hop3-test build-ready-image` is referenced (in `targets/docker.py`'s `_start_prebuilt` hint and the docs) as the way to build `hop3-ready:latest`, but the command does not exist. The fast app-test path therefore has no working build instruction; the intended ready-image lifecycle must be documented or restored.

- **Phase 0: cheap wins.** Add `make test-fast`. Make `c_e2e` reuse the cached image. Delete the dead `ci.yml`. Rename `d_e2e → c_e2e`; dissolve `c_system`. *(Hold the `testpaths` edit until the bare-`pytest` default is decided.)*
- **Phase 1: the silent-502 fix.** Build `collect_diagnostic_bundle` (proxy probe first); wire it into `hop3-test system` and the pytest `c_e2e` fixtures; add `hop3-test why` + the classifier + a bundle-aware result store. Revive the disabled proxy tests into `c_e2e`.
- **Phase 2: tiers + entry points.** Add the autouse marker-stamping hook; define `fast`/`check`; consolidate the Makefile (§5); bring `installer/rootd/tui/testing` into `check` and CI (rootd first, per [ADR 041](./041-privileged-operations-agent.md)); fix `.builds/`; update docs to the true surface.
- **Phase 3: absorb demos + tutorials.** Promote demos and tutorials to catalog entries through the ABC; preserve the `--narrate` timing reporter; wire the HTML report into nightly. Run side-by-side with the old harnesses for one nightly parity cycle.
- **Phase 4: cleanup (after parity).** Delete `scripts/run-all-tutorials*`, `runners/validations.py::_validate_validoc`, the redundant result DB, and the dead Makefile targets. Trim `nox` to `lint` + fast `pytest` + `audit`. Keep the demo engine.

## Consequences

- A contributor learns three runners and four tiers, all of which work, replacing a large mostly-broken surface.
- The daily inner loop drops to < 1 min and can never accidentally trigger a Docker build.
- The most common deployment failure (silent-502) gains a one-line diagnosis on every surface; failure history becomes queryable; nightly produces an HTML report.
- Previously-untested-in-CI packages (incl. security-sensitive `rootd`) enter the gate.
- The duplicated harness code is deleted; all deploy paths route through one primitive (consistent with "Hop3 is responsible for making things work" and functional-core/imperative-shell).
- Cost: real implementation work in `hop3-testing` for Phases 1 and 3; CI coordination for the GitHub→SourceHut clarification and any required branch-protection checks.

## Resolved decisions

Points that could have been left open are resolved as follows:

1. **Bare-`pytest` default.** The `testpaths` default is the in-process layers only (`a_unit` + `b_integration`); the Docker `c_e2e` layer is excluded, so a reflexive `pytest` never triggers Docker and CI invokes `c_e2e` explicitly.
2. **GitHub Actions.** All three vestigial workflows (`ci.yml`, `test.yml`, `e2e.yml`) are removed; SourceHut is the sole CI.
3. **Supported-Python contract.** 3.11–3.14 (`requires-python = ">=3.11,<3.15"`); `nox` fans out across those. 3.10 and 3.15 are dropped.
4. **Postgres-backup test placement.** The real-deploy `c_e2e` backup test (`c_e2e/test_backup.py`) owns the coverage; the legacy `c_system` variant is retired.
5. **`check` naming.** `make check` stays the lint alias; the check *tier* is `make test`.
6. **Bundle retention.** Build logs are auto-pruned to a recent-run count (`[retention].keep_runs`, via `hop3-test prune`).
