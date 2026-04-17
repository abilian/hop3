# Experience Report: Miniflux

**Status:** Draft (0.5)
**App:** Miniflux — RSS reader
**Language:** Go
**Database:** PostgreSQL
**Website:** https://miniflux.app/

## Deployment Methods

### Native (local builder)

- **Builder/Toolchain:** local/generic
- **Addons:** PostgreSQL
- **Build steps:** Build from source (make)
- **Status:** Passing
- **Issues:** None

### Nix (hand-crafted hop3.nix)

- **Template equivalent:** prebuilt-binary
- **Addons:** PostgreSQL
- **Status:** Passing
- **Issues:** None

### Nix (template-generated)

- **Template:** prebuilt-binary
- **Key config:** Environment variable driven (no config file generation)
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
Nix derivation, estimated at low (small Go project, no CGO, no frontend) effort.

## Lessons Learned

- Simplest Go app to package: single binary with environment-variable-only configuration.
- Native builds from source using make, but Nix uses a pre-built binary, showing how deployment methods can diverge in build strategy while producing the same result.
- DATABASE_URL is the only required configuration, making this app ideal for testing minimal PostgreSQL addon integration.

## Cross-Method Comparison

All methods pass cleanly. Miniflux is the simplest Go app in the set due to its single-binary, env-var-only design, making it a good baseline for testing Go deployment pipelines. The pre-built binary approach limits deployment to x86_64-linux; ARM and other architectures are not currently supported.
