---
app: grafana
title: Grafana
version: "10.3.1"
upstream: https://grafana.com/
languages: [go]
databases: []
in_catalog: false
report_status: withdrawn
last_verified: 2026-04-09
verified_bar: http-status

variants:
  native: {status: not-attempted}
  docker: {status: not-attempted}
  nix: {status: not-attempted}
  nix-gen: {status: not-attempted}
---
# Experience Report: Grafana

> **Withdrawn.** Grafana is no longer part of the packaged corpus and is not published in the catalog, so nothing here is maintained or re-verified. It is kept because the packaging work was real and the findings below may still save someone time. Everything it says was measured at the *deployed and serving* bar — not by signing in — which is the bar the current reports reject.

**Status:** Draft (0.5)
**App:** Grafana — Monitoring dashboard
**Language:** Go
**Database:** None (SQLite)
**Website:** https://grafana.com/

## Deployment Methods

### Native (local builder)

- **Builder/Toolchain:** local/generic
- **Addons:** None
- **Build steps:** Pre-built binary download (no source compilation)
- **Status:** Passing
- **Issues:** None

### Nix (hand-crafted hop3.nix)

- **Template equivalent:** prebuilt-archive
- **Addons:** None
- **Status:** Passing
- **Issues:** None

### Nix (template-generated)

- **Template:** prebuilt-archive
- **Key config:** custom.ini config generation
- **Addons:** None
- **Status:** Passing
- **Issues:** None

### Docker

- **Base image:** debian:trixie-slim
- **Addons:** None
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
Nix derivation, estimated at significant (Go backend + Node/Webpack frontend) effort.

## Lessons Learned

- No database addon is needed since Grafana uses embedded SQLite, making this the simplest Go app to package.
- The pre-built archive includes both the binary and required static assets (dashboards, plugins, frontend), so the archive template is more appropriate than the binary template.
- A start-timeout configuration is needed because Grafana takes a few seconds to initialize on first startup.
- SQLite-based apps avoid all database provisioning complexity, making them ideal early test cases.

## Cross-Method Comparison

Grafana is uniformly simple across all deployment methods due to its use of SQLite and pre-built distribution. The only configuration needed is a custom.ini file and appropriate start-timeout, both of which are trivial in every method. However, the pre-built archive limits deployment to x86_64-linux; ARM and other architectures are not currently supported.
