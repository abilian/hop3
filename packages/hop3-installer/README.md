# Hop3 Installer

Modular installer package for the Hop3 CLI and Server components.

## Overview

This package provides:

1. **Modular source code** for installers (`src/hop3_installer/`)
2. **Bundler script** to generate single-file installers
3. **Testing framework** for validating installers across multiple environments

## Structure

```
packages/hop3-installer/
├── pyproject.toml              # Package configuration
├── README.md                   # This file
└── src/hop3_installer/
    ├── __init__.py
    ├── common.py               # Shared utilities (Colors, Spinner, etc.)
    ├── bundler.py              # Single-file bundler script
    ├── cli/
    │   ├── __init__.py
    │   ├── config.py           # CLI installer configuration
    │   └── installer.py        # CLI installer logic
    ├── server/
    │   ├── __init__.py
    │   ├── config.py           # Server installer configuration
    │   └── installer.py        # Server installer logic
    └── testing/
        ├── __init__.py
        ├── common.py           # Test utilities
        ├── runner.py           # Test runner
        ├── validators.py       # Installation validators
        └── backends/
            ├── __init__.py
            ├── base.py         # Backend abstract base class
            ├── docker.py       # Docker container backend
            ├── ssh.py          # SSH remote backend
            └── vagrant.py      # Vagrant VM backend
```

## Usage

### Development

Install the package in development mode:

```bash
cd packages/hop3-installer
pip install -e .
```

### Generate Single-File Installers

Bundle the modular source into standalone scripts:

```bash
# Generate both installers
python -m hop3_installer.bundler --all --output-dir dist/

# Generate specific installer
python -m hop3_installer.bundler --type cli --output install-cli.py
python -m hop3_installer.bundler --type server --output install-server.py
```

### Run Installers Directly (for development)

```bash
# CLI installer
python -m hop3_installer.cli --help

# Server installer (requires root)
sudo python -m hop3_installer.server --help
```

### Testing

Run installer tests using different backends:

```bash
# SSH (remote server)
python -m hop3_installer.testing.main ssh --host user@server.example.com

# Docker (containers)
python -m hop3_installer.testing.main docker --distro ubuntu

# Vagrant (VMs)
python -m hop3_installer.testing.main vagrant --vm ubuntu
```

## Design Principles

1. **Single-file distribution**: Production installers are standalone Python scripts
2. **Standard library only**: No external dependencies for installers
3. **Modular development**: Code is organized into modules for maintainability
4. **Comprehensive testing**: Multiple backends for testing different environments

## Generating Releases

When releasing, generate fresh single-file installers:

```bash
# From project root
cd packages/hop3-installer
python -m hop3_installer.bundler --all --output-dir ../../installer/
```

The generated files can be:
- Served from `https://hop3.cloud/install-cli.py` and `install-server.py`
- Used with `curl -LsSf URL | python3 -`
- Downloaded and run directly

## License

Apache-2.0 - Copyright (c) 2025, Abilian SAS
