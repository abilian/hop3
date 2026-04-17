# Experience Report: Vikunja

**Status:** Draft (0.5)
**App:** Vikunja — Task management (Todoist alternative)
**Language:** Go
**Database:** PostgreSQL
**Website:** https://vikunja.io/

## Deployment Methods

### Native (local builder)

- **Builder/Toolchain:** local/generic
- **Addons:** PostgreSQL
- **Build steps:** Pre-built binary extracted from archive
- **Status:** Passing
- **Issues:** None

### Nix (hand-crafted hop3.nix)

- **Template equivalent:** prebuilt-archive
- **Addons:** PostgreSQL
- **Status:** Passing
- **Issues:** None

### Nix (template-generated)

- **Template:** prebuilt-archive
- **Key config:** ZIP archive extraction, config.yml generation
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
Nix derivation, estimated at moderate (Go backend + Vue frontend) effort.

## Lessons Learned

- YAML config generation works well for Go apps that expect a config.yml file.
- ZIP archive extraction is supported alongside tar.gz, broadening the prebuilt-archive template's applicability.
- Follows a consistent pre-built binary pattern shared with Mattermost and Miniflux, confirming that Go apps are straightforward to package.

## Cross-Method Comparison

All deployment methods pass cleanly. Vikunja follows the same pre-built Go binary pattern as other Go apps in the set, with YAML config generation being the only notable difference from the JSON-based Mattermost config. The pre-built binary approach limits deployment to x86_64-linux; ARM and other architectures are not currently supported.
