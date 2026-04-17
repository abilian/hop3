# Experience Report: Gitea

**Status:** Draft (0.5)
**App:** Gitea — Self-hosted Git
**Language:** Go
**Database:** PostgreSQL
**Website:** https://gitea.io/

## Deployment Methods

### Native (local builder)

- **Builder/Toolchain:** local/generic
- **Addons:** PostgreSQL
- **Build steps:** Pre-built binary download (no source compilation)
- **Status:** Passing
- **Issues:** None

### Nix (hand-crafted hop3.nix)

- **Template equivalent:** prebuilt-binary
- **Addons:** PostgreSQL
- **Status:** Passing
- **Issues:** None

### Nix (template-generated)

- **Template:** prebuilt-binary
- **Key config:** app.ini config generation via [nix.config-files] (INI format)
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
Nix derivation, estimated at moderate (large Go project, no frontend build) effort.

## Lessons Learned

- Pre-built Go binaries are expedient but not a long-term solution: while they offer a single static binary with no runtime dependencies and fast startup, they sacrifice reproducibility and architecture portability.
- INI config generation via [nix.config-files] works well for apps like Gitea that use traditional INI-style configuration.
- Gitea requires a specific `custom/conf/` directory structure for its configuration, which must be set up correctly in all deployment methods.
- Go apps with pre-built binaries have the most uniform experience across all deployment methods.

## Cross-Method Comparison

All four methods are nearly equivalent in complexity since Gitea ships as a single binary. The only variation is how the app.ini configuration file is generated and placed in the custom/conf/ directory, which each method handles slightly differently. Note that the pre-built binary approach limits deployment to x86_64-linux; ARM and other architectures are not currently supported.
