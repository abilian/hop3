# Experience Report: Mattermost

**Status:** Draft (0.5)
**App:** Mattermost — Team chat
**Language:** Go
**Database:** PostgreSQL
**Website:** https://mattermost.com/

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
- **Key config:** Complex pre-exec (asset symlinking), config.json generation from environment variables
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
Nix derivation, estimated at significant (Go backend + React frontend) effort.

## Lessons Learned

- Pre-built Go archive includes both the binary and an asset directory (templates, i18n, static files).
- Needs symlinks from the writable data directory back to the Nix store for static assets, since Mattermost expects assets relative to its binary.
- JSON config generation from environment variables works well and avoids maintaining a separate config template.
- The pre-exec step for symlinking is more complex than most apps but follows a repeatable pattern.

## Cross-Method Comparison

All deployment methods pass. The main complexity is asset directory management, which the prebuilt-archive template handles via symlinking. Native and Docker deployments avoid this since assets live alongside the binary in a writable filesystem. The pre-built archive approach limits deployment to x86_64-linux; ARM and other architectures are not currently supported.
