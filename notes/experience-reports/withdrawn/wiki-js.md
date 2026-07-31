---
app: wiki-js
title: Wiki.js
version: "2.5.302"
upstream: https://js.wiki/
languages: [node]
databases: [postgres]
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
# Experience Report: Wiki.js

> **Withdrawn.** Wiki.js is no longer part of the packaged corpus and is not published in the catalog, so nothing here is maintained or re-verified. It is kept because the packaging work was real and the findings below may still save someone time. Everything it says was measured at the *deployed and serving* bar — not by signing in — which is the bar the current reports reject.

**Status:** Draft (0.5)
**App:** Wiki.js — Modern wiki
**Language:** Node.js
**Database:** PostgreSQL
**Website:** https://js.wiki/

## Deployment Methods

### Native (local builder)

- **Builder/Toolchain:** local/generic
- **Addons:** PostgreSQL
- **Build steps:** Pre-built release; started with `node server/index.js`
- **Status:** Passing
- **Issues:** None

### Nix (hand-crafted hop3.nix)

- **Template equivalent:** node-prebuilt
- **Addons:** PostgreSQL
- **Status:** Passing
- **Issues:** None

### Nix (template-generated)

- **Template:** node-prebuilt
- **Key config:** nodejs_22, asset symlinking, config.yml generation
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
Nix derivation, estimated at moderate (Node.js with build step) effort.

## Lessons Learned

- Only Node.js app in the set, making it the sole test case for the node-prebuilt template.
- The node-prebuilt template avoids npm install at build time by using a pre-built release archive, which significantly speeds up deployment.
- Needs careful asset directory symlinking similar to Mattermost, since Wiki.js expects assets in specific relative paths.
- YAML config generation (config.yml) works well and follows the same pattern as Vikunja.

## Cross-Method Comparison

All methods pass. Wiki.js validates the node-prebuilt template as a viable alternative to building from source, though pre-built releases sacrifice reproducibility and architecture portability (see Known Limitations). The asset symlinking requirement mirrors the pattern seen in Go apps like Mattermost, suggesting a shared solution for apps with bundled static assets. Only x86_64-linux is supported with the pre-built approach.
