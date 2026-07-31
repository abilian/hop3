---
app: focalboard
title: Focalboard
version: "7.11.4"
upstream: https://www.focalboard.com/
languages: [go]
databases: [postgres]
in_catalog: false
report_status: withdrawn
last_verified: 2026-04-09
verified_bar: http-status

variants:
  native: {status: no-recipe, reason: "dropped from the corpus with the application"}
  docker: {status: no-recipe, reason: "dropped from the corpus with the application"}
  nix: {status: no-recipe, reason: "dropped from the corpus with the application"}
  nix-gen: {status: no-recipe, reason: "dropped from the corpus with the application"}
---
# Experience Report: Focalboard

> **Withdrawn.** Focalboard is no longer part of the packaged corpus and is not published in the catalog, so nothing here is maintained or re-verified. It is kept because the packaging work was real and the findings below may still save someone time. Everything it says was measured at the *deployed and serving* bar — not by signing in — which is the bar the current reports reject.

**Status:** Draft (0.5)
**App:** Focalboard — Project management (Kanban)
**Language:** Go/Node hybrid
**Database:** PostgreSQL
**Website:** https://www.focalboard.com/

## Deployment Methods

### Native (local builder)

- **Builder/Toolchain:** local/go with complex build (make + npm)
- **Addons:** PostgreSQL
- **Build steps:** make (which runs Go compilation and npm build for frontend assets)
- **Status:** Passing
- **Issues:** None

### Nix (hand-crafted hop3.nix)

- **Template equivalent:** prebuilt-archive
- **Addons:** PostgreSQL
- **Status:** Passing
- **Issues:** None

### Nix (template-generated)

- **Template:** prebuilt-archive
- **Key config:** config.json generation from environment variables
- **Addons:** PostgreSQL
- **Status:** Passing
- **Issues:** None

### Docker

- **Base image:** debian:trixie-slim
- **Addons:** PostgreSQL
- **Status:** Passing
- **Issues:** None

## Known Limitations

**Pre-built binary reliance.** The Nix configurations (both hand-crafted
and template-generated) use pre-built binaries downloaded from upstream
releases. This is a pragmatic shortcut but has serious drawbacks:

- **Not reproducible:** The binary cannot be rebuilt from source by Nix.
  We trust the upstream CI pipeline.
- **Not portable:** Only x86_64-linux binaries are available. ARM
  (aarch64), RISC-V, and other architectures are not supported.
- **Supply chain risk:** A compromised upstream release could distribute
  malicious binaries.

**Path forward:** Build from source using `buildGoModule` (for Go apps)
or `buildNpmPackage` (for Node.js apps). This requires writing a proper
Nix derivation, estimated at significant (Go + Node hybrid build) effort.

## Lessons Learned

- Hybrid Go+Node apps are the hardest category to build natively because they require two full toolchains and a coordinated build process.
- Using a pre-built archive simplifies deployment enormously and sidesteps the dual-toolchain problem entirely.
- The config.json must be generated from environment variables at startup time, not at build time, to support per-environment configuration.
- This app demonstrates why the prebuilt-archive template exists: some apps are too complex to build reliably in every environment.

## Cross-Method Comparison

The pre-built archive approach (used by both Nix methods and Docker) is far simpler than the native build, which requires both Go and Node toolchains. For hybrid apps like Focalboard, pre-built artifacts are expedient but come with portability and reproducibility trade-offs (see Known Limitations). Only x86_64-linux is supported with this approach.
