# hop3-testing

Testing framework for Hop3 deployment validation.

## Overview

hop3-testing provides utilities and fixtures for testing Hop3 deployments. It supports running tests against Docker containers or remote servers, with a catalog of test applications covering various languages and frameworks.

## Features

- **Multiple targets** - Test against Docker containers or remote SSH servers
- **App catalog** - Pre-built test applications for various languages
- **Deployment sessions** - Automated deploy/verify/cleanup workflow
- **pytest fixtures** - Integration with pytest for E2E testing
- **Category filtering** - Run tests by language or framework

## Installation

### For development

```bash
# From workspace root
cd packages/hop3-testing
uv pip install -e ".[dev]"
```

## Quick Start

```bash
# Test all apps on Docker
hop3-test --target docker

# Test specific app
hop3-test --target docker 010-flask-pip-wsgi

# Test against remote server
hop3-test --target remote --host server.example.com

# Test specific category
hop3-test --target docker --category python-simple

# List available apps
hop3-test --list-apps
```

## Architecture

```
hop3-testing/
├── src/hop3_testing/
│   ├── main.py              # CLI entry point
│   ├── base.py              # Base test fixtures
│   ├── common.py            # Shared utilities
│   ├── apps/
│   │   ├── catalog.py       # App catalog management
│   │   └── deployment.py    # Deployment session handling
│   ├── targets/
│   │   ├── base.py          # Abstract target interface
│   │   ├── docker.py        # Docker container target
│   │   └── remote.py        # Remote SSH target
│   └── util/
│       ├── console.py       # Output formatting
│       └── backports.py     # Python compatibility
└── tests/
```

## Test Targets

### Docker Target

Runs tests in isolated Docker containers:

```bash
hop3-test --target docker --image ubuntu:24.04
```

### Remote Target

Runs tests against a remote Hop3 server:

```bash
hop3-test --target remote --host server.example.com --ssh-key ~/.ssh/id_rsa
```

## App Categories

Test applications are organized by category:

| Category | Languages/Frameworks |
|----------|---------------------|
| `python-simple` | Flask, FastAPI, Django |
| `python-complex` | Multi-process, workers |
| `nodejs` | Express, Fastify |
| `ruby` | Sinatra, Rails |
| `go` | Fiber, Gin |
| `rust` | Actix-web, Axum |
| `static` | HTML, Hugo, Jekyll |

## Using with pytest

```python
# conftest.py
from hop3_testing import DeploymentTarget, AppCatalog

@pytest.fixture(scope="session")
def deployment_target():
    """Provide a deployment target for tests."""
    return DockerTarget()

@pytest.fixture
def app_catalog():
    """Provide the test app catalog."""
    return AppCatalog()

# test_deployment.py
def test_flask_app(deployment_target, app_catalog):
    """Test Flask application deployment."""
    app = app_catalog.get("010-flask-pip-wsgi")

    with DeploymentSession(deployment_target, app) as session:
        session.deploy()
        assert session.verify_running()
        assert session.verify_http_response()
```

## Development

### Running tests

```bash
# From package directory
uv run pytest tests/ -v

# With coverage
uv run pytest tests/ --cov=hop3_testing
```

### Code quality

```bash
uv run ruff check src/
uv run ruff format src/
```

## Documentation

- **Testing Strategy**: [Testing guide](../../docs/src/dev/testing-strategy.md)
- **System Architecture**: [Architecture overview](../../docs/src/dev/architecture.md)
- **Package Internals**: [Deep-dive documentation](./docs/internals.md)

## Related Packages

- [hop3-server](../hop3-server/) - The server being tested
- [hop3-cli](../hop3-cli/) - CLI used for deployments in tests

## License

Apache-2.0 - Copyright (c) 2024-2025, Abilian SAS
