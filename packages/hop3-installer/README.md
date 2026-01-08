# hop3-installer

Installation toolkit for deploying Hop3 to servers and containers.

## Overview

hop3-installer provides two main tools:
- **hop3-install** - Production installer for end users and sysadmins
- **hop3-deploy** - Developer tool for deploying during development

The installers use only Python standard library, making them easy to distribute as single-file scripts.

## Features

- **Single-file distribution** - Bundle into standalone Python scripts
- **No dependencies** - Uses only Python stdlib for maximum portability
- **Multiple backends** - Test on Docker, SSH, or Vagrant
- **Developer workflow** - Deploy local code changes for testing

## Installation

### For development

```bash
# From workspace root
cd packages/hop3-installer
uv pip install -e ".[dev]"
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

## Architecture

```
hop3-installer/
├── src/hop3_installer/
│   ├── cli/                 # CLI installer
│   │   ├── config.py        # Configuration
│   │   └── installer.py     # Installation logic
│   ├── server/              # Server installer
│   │   ├── config.py        # Configuration
│   │   └── installer.py     # Installation logic
│   ├── deployer/            # Developer deployment tool
│   │   ├── cli.py           # CLI interface
│   │   ├── deploy.py        # Deployment logic
│   │   └── backends/        # SSH, Docker backends
│   ├── testing/             # Test framework
│   │   ├── runner.py        # Test execution
│   │   ├── validators.py    # Installation checks
│   │   └── backends/        # Docker, SSH, Vagrant
│   ├── bundler.py           # Single-file bundler
│   └── common.py            # Shared utilities
└── tests/
```

## Commands

### hop3-install

| Subcommand | Description |
|------------|-------------|
| `cli` | Install hop3-cli on local machine |
| `server` | Install hop3-server (requires root) |
| `bundle` | Generate single-file installers |

### hop3-deploy

| Option | Description |
|--------|-------------|
| `--host HOST` | Target server hostname |
| `--docker` | Deploy to Docker container |
| `--local` | Upload and use local code |
| `--clean` | Clean existing installation |
| `--admin-domain` | Set up admin interface |

## Development

### Generate single-file installers

```bash
# Generate both installers
hop3-install bundle --all --output-dir dist/

# Generate specific installer
hop3-install bundle --type server --output install-server.py
```

### Running tests

```bash
# From package directory
uv run pytest tests/ -v

# Test installers on Docker
hop3-test-installers docker --distro ubuntu

# Test on remote server
hop3-test-installers ssh --host user@server.example.com
```

### Code quality

```bash
uv run ruff check src/
uv run ruff format src/
```

## Documentation

- **Installation Guide**: [Main documentation](../../docs/src/installation.md)
- **Installer Details**: [Installer documentation](../../docs/src/installer.md)
- **Installer Testing**: [Testing guide](../../docs/src/dev/installer-testing.md)
- **Package Internals**: [Deep-dive documentation](./docs/internals.md)

## Related Packages

- [hop3-server](../hop3-server/) - The server component installed by this package
- [hop3-cli](../hop3-cli/) - The CLI component installed by this package

## License

Apache-2.0 - Copyright (c) 2024-2026, Abilian SAS
