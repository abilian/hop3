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
