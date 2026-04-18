# Notes

Developer-facing notes for Hop3. The entries below cover what lives where.

## Top-level

- [`app-porting-tips.md`](./app-porting-tips.md) — cookbook for packaging a self-hosted application as a Hop3 app, distilled from ~30 real apps packaged between late 2025 and April 2026.
- [`questions.md`](./questions.md) — open architectural questions (pointer to relevant ADRs).

## `adrs/` — Architecture Decision Records

ADRs record the "why" behind architectural choices — plugin system, build/runtime separation, Nix integration, CLI ergonomics, Python deploy strategies, multi-service apps, and more. The ADR index is in [`adrs/`](./adrs/).

## `reports/` — Technical reports

- [`TR-01.md`](./reports/TR-01.md) — Hop3 technical report (interim), with: abstract, related work, system design, evaluation, threats, references.
- `draft-paper.md` — draft research paper material.

## `ngi-2024/` — NGI project documents

- [`project-plan.md`](./ngi-2024/project-plan.md) — NGI project plan (T1–T5 tasks, M-series milestones).
- [`release-plan-0.5.md`](./ngi-2024/release-plan-0.5.md) — 0.5 release scope and DoD (active).
- [`release-plan-0.6.md`](./ngi-2024/release-plan-0.6.md) — 0.6 future release plan (paper submission, screencasts, Nix Phase 3).
- [`plan-source-builds.md`](./ngi-2024/plan-source-builds.md) — historical plan for Go-app source builds (✅ done; preserved as record).

## `experience-reports/` — Packaging experience per app

21 per-app reports (00–20) aggregated in [`experience-reports/00-aggregate.md`](./experience-reports/00-aggregate.md). Each covers deployment attempts, surprises, workarounds, and what would have helped.

## `lessons-learned/` — Topic-specific deep dives

- [`00README.md`](./lessons-learned/00README.md) — index + numbered quick-reference lessons.
- [`database-addon-portability.md`](./lessons-learned/database-addon-portability.md) — PostgreSQL / MySQL connectivity across native and Docker.
- [`deployment-diagnostics.md`](./lessons-learned/deployment-diagnostics.md) — making deploy failures actionable.
- [`e2e-test-infrastructure.md`](./lessons-learned/e2e-test-infrastructure.md) — building and running the E2E suite.
- [`multi-distribution-support.md`](./lessons-learned/multi-distribution-support.md) — Debian / Red Hat / Fedora parity patterns.
- [`native-apps-caveats.md`](./lessons-learned/native-apps-caveats.md) — caveats specific to `builder = "local"`.
- [`nix-packaging.md`](./lessons-learned/nix-packaging.md) — Nix integration gotchas.
- [`uwsgi-daemon-management.md`](./lessons-learned/uwsgi-daemon-management.md) — emperor / vassal lifecycle, `attach-daemon` env propagation.

## `testing/` — Test framework notes

- [`strategy.md`](./testing/strategy.md) — overall testing strategy.
- [`cheat-sheet.md`](./testing/cheat-sheet.md) — quick-reference for testing commands.
- [`status.md`](./testing/status.md) — current test suite status.
- [`demos.md`](./testing/demos.md) — how to run the demo apps.

## `dev/` — Developer guides

- [`docker-debug.md`](./dev/docker-debug.md) — interactive Docker-container debugging recipes.
- [`implementing-service-backup.md`](./dev/implementing-service-backup.md) — how to add backup/restore to a service plugin.

## `tui/` — Terminal UI specs

- [`01-features.md`](./tui/01-features.md) — hop3-tui feature specification.
- [`02-feature-parity.md`](./tui/02-feature-parity.md) — feature parity tracker between hop3-cli and hop3-tui.

## `archive/` — Superseded historical notes

- [`README.md`](./archive/README.md) — what's archived and why.
- `config.md`, `current-status.md`, `documentation.md`, `roadmap.md` — pre-0.4 snapshots preserved for context.
