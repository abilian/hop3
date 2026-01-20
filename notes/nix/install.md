# Hop3 Nix Installation Guide

This guide covers building and running Hop3 packages with Nix.

## Prerequisites

- Nix with flakes enabled
- See `notes/nix/prepare.md` for Nix installation on Ubuntu

## Development Shell

Enter the development environment with all dependencies:

```bash
nix develop
```

This provides Python 3.12, uv, and system dependencies. Then install Python packages:

```bash
uv sync
```

## Building Packages

Build individual packages:

```bash
# Build hop3-cli
nix build .#hop3-cli

# Build hop3-server
nix build .#hop3-server
```

The built package is symlinked to `./result/`.

## Running Packages

### Option 1: Direct run (recommended for quick testing)

```bash
nix run .#hop3 -- --version
nix run .#hop3-server -- serve --help
```

### Option 2: Run from build result

```bash
nix build .#hop3-cli
./result/bin/hop3 --version
```

### Option 3: Temporary shell with packages

```bash
# Single package
nix shell .#hop3-cli
hop3 --version

# Multiple packages
nix shell .#hop3-cli .#hop3-server
```

### Option 4: Install to user profile (persistent)

```bash
nix profile install .#hop3-cli
```

After installing to profile, ensure `~/.nix-profile/bin` is in your PATH:

```bash
export PATH="$HOME/.nix-profile/bin:$PATH"
```

Add this line to `~/.bashrc` or `~/.profile` to make it permanent.

To uninstall:

```bash
nix profile remove hop3-cli
```

## Verifying Installation

```bash
hop3 --version
# Output: hop3-cli 0.4.0b1
```

## Troubleshooting

### "command not found" after profile install

The nix profile bin directory isn't in PATH. Either:

1. Add to PATH: `export PATH="$HOME/.nix-profile/bin:$PATH"`
2. Source nix profile: `source /etc/profile.d/nix.sh`
3. Log out and log back in

### Build fails with hash mismatch

The flake.lock may be stale. Update it:

```bash
nix flake update
```

### OOM during granian build

The hop3-server package uses uvicorn instead of granian to avoid OOM issues during the Rust compilation. This is handled automatically in the flake.

## Package Notes

The Nix build patches some dependencies:

| Original | Nix Version | Reason |
|----------|-------------|--------|
| uv-build | hatchling | uv-build not in nixpkgs |
| granian | uvicorn | OOM during Rust build |
| psycopg2-binary | psycopg2 | Binary wheels not used in Nix |
| paramiko<3 | paramiko>=2.11 | nixpkgs has paramiko 4.x |

Removed dependencies (not in nixpkgs, optional at runtime):
- cyclonedx-bom
- mysql-connector-python
- uwsgi
