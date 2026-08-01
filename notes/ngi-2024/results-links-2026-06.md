# NGI #2024-04-365: Links to achieved results (per milestone) - Interim Report

Status: final
Date: 24 June 2026

Evidence for the NLNet/NGI "verify these results" field, one entry per milestone. Documentation links resolve on <https://hop3.cloud/> (live at submission); code is on SourceHut (`sfermigier/hop3`), with a mirror on GitHUb (`abilian/hop3`); ADRs carry the design rationale.

## T1: Nix Build Plugins

**M1.1: Nix "native" builder (apps with a Nix expression)** ✅

- <https://hop3.cloud/guides/nix-deployment/>: guide: deploying an app from a `hop3.nix` expression
- <https://hop3.cloud/reference/nix/>: `hop3.nix` / `[nix]` reference
- <https://hop3.cloud/developers/adrs/006-nix-integration/>: design decision
- <https://git.sr.ht/~sfermigier/hop3/tree/main/packages/hop3-server/src/hop3/plugins/build/nix>: the NixBuilder (reads `hop3.nix`, runs `nix-build`, extracts `runtime.json`)
- <https://git.sr.ht/~sfermigier/hop3/tree/main/apps/real-apps-nix>: 33 hand-crafted `hop3.nix` apps, deployed & verified via `hop3-test` and `hop3-testlab`.

**M1.2: Nix alternatives to existing builders (Python/Node/Ruby/Go/Rust/Java), 12-factor** ✅

- <https://hop3.cloud/developers/adrs/008-nix-builders-2/>: template-based generation from `[nix]` (8 templates incl. `nixpkgs-wrapper`, `python-venv`, `node-prebuilt`, `ruby-bundler`, `java-war`); rationale for replacing Dream2nix is inside
- <https://git.sr.ht/~sfermigier/hop3/tree/main/packages/hop3-server/src/hop3/plugins/build/nix/gen/templates>: generator, templates, `nix eject`
- <https://git.sr.ht/~sfermigier/hop3/tree/main/apps/real-apps-nix-gen>: 30 template-generated apps validated via `hop3-test`

## T2: Nix Runtime

**M2.1: Specifications & PoC** ✅

- <https://hop3.cloud/developers/adrs/035-build-artifacts/>: the runtime contract: `BuildArtifact`/`RuntimeConfig` carries Nix store paths, env, workers (`runtime.json`)
- <https://hop3.cloud/blog/posts/2026-03-build-artifact-pattern/>: blog explaining the build/run separation (the PoC mechanism)

**M2.2: Beta (≈90%; a few upstream apps deferred)**: the 33 + 30 Nix apps above run end-to-end on the Nix runtime via the uWSGI deployer ✅

- <https://git.sr.ht/~sfermigier/hop3/tree/main/apps/bad>: per-app `DEFERRED.md` notes documenting where an upstream app can't be Nix-built (each points at a platform gap)

## T3: Security & Resilience

**M3.1: Backing services**: *PostgreSQL/MySQL/Redis/S3 shipped; full operational command set + resource limits & volumes added in 0.6; experimental email/SMTP relay addon added in 0.6* ✅

- <https://hop3.cloud/guides/addons/>: guide: PostgreSQL, MySQL, Redis, S3/MinIO addons
- <https://hop3.cloud/developers/adrs/046-declarative-app-resources/>: declarative `[[addons]]`, generated secrets/env, and (Phase 2) `[limits]` resource caps + volumes
- <https://git.sr.ht/~sfermigier/hop3/tree/main/packages/hop3-server/src/hop3/plugins>: `postgresql/`, `mysql/`, `redis/`, `s3/`, `email/` plugins; 0.6 adds the `addon <type> <verb>` surface (query/diagnostics/clone/export-import/expose/promote/endpoint) and `hop3 tunnel`

**M3.4: Testing framework & infrastructure** ✅

- <https://hop3.cloud/blog/posts/2026-06-how-hop3-is-tested/>: overview (start of a 5-part series)
- <https://hop3.cloud/developers/adrs/043-unified-testing-architecture/>: unified testing architecture
- <https://hop3.cloud/developers/adrs/044-nightly-test-lab/>: the nightly Test Lab
- <https://hop3.cloud/developers/testing-strategy/>: testing strategy doc
- <https://git.sr.ht/~sfermigier/hop3/tree/main/packages/hop3-testing>: the `hop3-test` runner (Docker/SSH/cloud targets; 100+ app and demos catalog)
- CI on SourceHut: <https://builds.sr.ht/~sfermigier/hop3/commits>
- Testlab demo: <https://testlab.hop3-dev.abilian.com/>

**M3.6: CLI (basic)** ✅

- <https://hop3.cloud/reference/cli/>: full CLI reference (~120 commands, space-separated, `--app` model)
- <https://hop3.cloud/developers/adrs/036-cli-ergonomics/>: CLI ergonomics & command surface
- <https://hop3.cloud/developers/adrs/042-cli-context-model/>: servers & project contexts
- <https://hop3.cloud/guides/cli-migration/>: migration from the old colon syntax
- <https://git.sr.ht/~sfermigier/hop3/tree/main/packages/hop3-cli>

## T5: Dissemination & Engagement

**M5.1: Website & blog** ✅

- <https://hop3.cloud/> and <https://hop3.cloud/blog/>: 23 posts (release notes, architecture, security, the 5-part testing series, a "migrating from X" series, conference write-ups)

**M5.2: Documentation (devs/admins/end-users)** ✅

- <https://hop3.cloud/guides/> · <https://hop3.cloud/reference/> · <https://hop3.cloud/developers/> · <https://hop3.cloud/tutorials/>: and 51 published ADRs at <https://hop3.cloud/developers/adrs/>

**M5.4: Conference presentation / workshop** ✅

- <https://hop3.cloud/blog/posts/2025-06-ow2con/>: Hop3 at OW2Con 2025
- <https://hop3.cloud/blog/posts/2025-12-osxp/>: Hop3 at OSXP 2025
- <https://hop3.cloud/blog/posts/2026-06-ow2con/>: Hop3 at OW2Con 2026
