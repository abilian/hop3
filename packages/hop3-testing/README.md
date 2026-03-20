# hop3-testing

Testing framework for Hop3 deployment validation.

## Overview

hop3-testing provides utilities and fixtures for testing Hop3 deployments. It supports running tests against Docker containers or remote servers, with a catalog of test applications covering various languages and frameworks.

## Features

- **Multiple targets**: Test against Docker containers or remote SSH servers
- **App catalog**: Pre-built test applications for various languages
- **Deployment sessions**: Automated deploy/verify/cleanup workflow
- **pytest fixtures**: Integration with pytest for E2E testing
- **Category filtering**: Run tests by language or framework

## Installation

```bash
pip install hop3-testing
```

## Quick Start

```bash
# List available tests
hop3-test list

# Run system tests on Docker
hop3-test system --docker

# Test specific apps
hop3-test apps 010-flask-pip-wsgi

# Test against remote server
hop3-test apps --host server.example.com

# Run CI tests
hop3-test ci
```

## Commands

| Command | Description |
|---------|-------------|
| `hop3-test system` | Deploy Hop3 and run system tests |
| `hop3-test apps` | Test apps against pre-deployed Hop3 |
| `hop3-test list` | List available tests |
| `hop3-test show <name>` | Show test details |
| `hop3-test ci` | Run CI tests (fast+medium, P0) |
| `hop3-test dev` | Run developer tests (fast, P0 only) |
| `hop3-test hetzner` | Run E2E tests on Hetzner Cloud |
| `hop3-test multi-distro` | Test across multiple Linux distributions |

### Common Options

| Option | Description |
|--------|-------------|
| `-v, --verbose` | Verbose output |
| `--fail-fast` | Stop on first failure |
| `--keep` | Keep apps deployed after testing |
| `--docker` | Use Docker target |
| `--host HOST` | Remote server hostname |

## Architecture

```
hop3-testing/
├── src/hop3_testing/
│   ├── cli/              # CLI commands
│   │   └── commands/     # Click command implementations
│   ├── catalog/          # Test discovery
│   │   ├── scanner.py    # Discovers test.toml files
│   │   └── models.py     # TestDefinition, Category
│   ├── apps/
│   │   ├── catalog.py    # AppSource dataclass
│   │   └── deployment.py # DeploymentSession
│   ├── targets/
│   │   ├── base.py       # DeploymentTarget ABC
│   │   ├── docker.py     # DockerTarget
│   │   └── remote.py     # RemoteTarget
│   └── results/          # Result storage and reporting
└── tests/
```

## Test Categories

| Category | Languages/Frameworks |
|----------|---------------------|
| `python` | Flask, FastAPI, Django |
| `nodejs` | Express, Fastify |
| `ruby` | Sinatra, Rails |
| `go` | Fiber, Gin |
| `rust` | Actix-web, Axum |
| `static` | HTML, Hugo, Jekyll |

## Hetzner Cloud Testing

Run full E2E tests on real Hetzner Cloud servers. Requires `HETZNER_API_TOKEN` environment variable.

```bash
# List available images
hop3-test multi-distro --list-images

# Run tests on a single distribution
hop3-test hetzner --image ubuntu-24.04 --suites test-apps

# Run tests across multiple distributions
hop3-test multi-distro --images ubuntu-24.04 debian-13 fedora-42

# Use local code instead of git
hop3-test hetzner --use-local-repo

# Skip phases for debugging
hop3-test hetzner --skip-reset    # Keep existing server state
hop3-test hetzner --skip-deploy   # Use existing Hop3 installation
hop3-test hetzner --skip-tests    # Only reset and deploy
```

### Hetzner Options

| Option | Description |
|--------|-------------|
| `--server-id ID` | Use specific Hetzner server |
| `--image IMAGE` | OS image (e.g., ubuntu-24.04) |
| `--branch BRANCH` | Git branch to test (default: devel) |
| `--use-local-repo` | Deploy from local code |
| `--skip-reset` | Skip server reset |
| `--skip-deploy` | Skip Hop3 deployment |
| `--suites SUITE` | Test suites to run |
| `--continue-on-failure` | Don't stop on first failure (multi-distro) |

## Development

```bash
# Run tests
uv run pytest tests/ -v

# Lint and format
uv run ruff check src/
uv run ruff format src/
```

## Documentation

- [Testing Strategy](../../docs/src/dev/testing-strategy.md)

## Related Packages

- [hop3-server](../hop3-server/) - The server being tested
- [hop3-cli](../hop3-cli/) - CLI used for deployments in tests

## License

Apache-2.0 - Copyright (c) 2024-2026, Abilian SAS
