# Using the Hop3 Nix Flake

This documents how to use the Nix flake for Hop3 development and deployment.

## Prerequisites

Ensure you have Nix with flakes enabled. See `./prepare.md` for setup instructions.

## Development Shell

Enter a development shell with all dependencies:

```bash
nix develop
```

This provides:
- Python 3.12 with build tools
- uv (modern Python package manager)
- Git, Make
- PostgreSQL and SQLite clients
- GCC and OpenSSL for native extensions

Inside the shell, install dependencies with:
```bash
uv sync
```

## Building Packages

### Build hop3-cli

```bash
nix build .#hop3-cli
```

The result is in `./result/bin/hop3`.

### Build hop3-server

```bash
nix build .#hop3-server
```

The result is in `./result/bin/hop3-server`.

### Build default package (hop3-cli)

```bash
nix build
```

## Running Without Installing

```bash
# Run hop3 CLI
nix run .#hop3 -- --help

# Run hop3-server
nix run .#hop3-server -- serve --help
```

## Inspecting the Flake

```bash
# Show all outputs
nix flake show

# Check flake validity
nix flake check
```

## NixOS Module

For deploying on NixOS, import the module in your configuration:

```nix
# In your NixOS configuration (e.g., configuration.nix)
{
  imports = [
    (builtins.getFlake "github:abilian/hop3").nixosModules.default
  ];

  services.hop3 = {
    enable = true;
    port = 8000;
    secretKeyFile = "/run/secrets/hop3-secret";
  };
}
```

### Module Options

| Option | Default | Description |
|--------|---------|-------------|
| `enable` | `false` | Enable Hop3 service |
| `user` | `"hop3"` | System user for the service |
| `group` | `"hop3"` | System group |
| `homeDir` | `/home/hop3` | Hop3 home directory |
| `port` | `8000` | API server port |
| `secretKeyFile` | `null` | Path to JWT secret key file |

## Troubleshooting

### Missing Python packages

Some dependencies like `advanced-alchemy`, `cyclonedx-bom`, and `mysql-connector-python` may not be in nixpkgs. These are commented out in the flake and may need custom overlays.

### Build failures

If a package fails to build:

1. Check if all dependencies are available:
   ```bash
   nix search nixpkgs python312Packages.<package-name>
   ```

2. Some packages use `uv-build` as their build backend, which may not be recognized. The flake uses `hatchling` as a fallback.

### Updating dependencies

```bash
# Update all flake inputs
nix flake update

# Update a specific input
nix flake lock --update-input nixpkgs
```

## Local Development with Nix

For a hybrid approach using Nix for system deps and uv for Python:

```bash
# Enter nix shell
nix develop

# Use uv for Python packages
uv sync

# Run tests
pytest
```

This gives you reproducible system dependencies while keeping Python package management familiar.
