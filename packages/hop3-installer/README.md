# hop3-installer

Installation toolkit for deploying Hop3 to servers and containers.

## Overview

hop3-installer provides two main tools:

- **hop3-install**: Production installer for end users and sysadmins
- **hop3-deploy**: Developer tool for deploying during development

The installers use only Python standard library, making them easy to distribute as single-file scripts.

## Features

- **Single-file distribution**: Bundle into standalone Python scripts
- **No dependencies**: Uses only Python stdlib for maximum portability
- **Multiple backends**: Deploy to Docker containers or remote servers via SSH
- **Developer workflow**: Deploy local code changes for testing

## Installation

```bash
pip install hop3-installer
```

## Quick Start

### Production Installation (hop3-install)

```bash
# Install hop3-cli on local machine
hop3-install cli

# Install hop3-server on current machine (run as root)
sudo hop3-install server

# Or use the one-liner
curl -LsSf https://hop3.cloud/install-server.py | sudo python3 -
```

### Developer Deployment (hop3-deploy)

```bash
# Deploy to remote server
export HOP3_DEV_HOST=server.example.com
hop3-deploy

# Deploy with local code changes
hop3-deploy --local

# Deploy to Docker container
hop3-deploy --docker

# Clean installation
hop3-deploy --clean
```

## Commands

### hop3-install

| Subcommand | Description |
|------------|-------------|
| `cli` | Install hop3-cli on local machine |
| `server` | Install hop3-server (requires root) |
| `bundle` | Generate single-file installers |
| `test` | Test installers on Docker or SSH targets |

### hop3-deploy

| Option | Description |
|--------|-------------|
| `--host HOST` | Target server hostname |
| `--docker` | Deploy to Docker container |
| `--local` | Upload and use local code |
| `--clean` | Clean existing installation |
| `--teardown` | Remove Docker container |

## Architecture

```
hop3-installer/
├── src/hop3_installer/
│   ├── main.py           # Entry point for hop3-install
│   ├── common.py         # Shared utilities (Colors, Spinner)
│   ├── bundler.py        # Single-file bundler
│   ├── cli/              # CLI installer
│   │   └── installer.py
│   ├── server/           # Server installer
│   │   └── installer.py
│   ├── deployer/         # Developer deployment (hop3-deploy)
│   │   ├── cli.py
│   │   ├── deploy.py
│   │   └── backends/     # SSH, Docker backends
│   └── testing/          # Installer validation
│       ├── runner.py
│       └── backends/
└── tests/
```

## Development

```bash
# Generate single-file installers
hop3-install bundle --all --output-dir dist/

# Test installers on Docker
hop3-install test docker --distro ubuntu

# Run tests
uv run pytest tests/ -v

# Lint and format
uv run ruff check src/
uv run ruff format src/
```

## Documentation

- [Installation Guide](../../docs/src/installation.md)

## Related Packages

- [hop3-server](../hop3-server/) - The server component installed by this package
- [hop3-cli](../hop3-cli/) - The CLI component installed by this package

## License

Apache-2.0 - Copyright (c) 2024-2026, Abilian SAS
