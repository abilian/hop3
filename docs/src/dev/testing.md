# Testing Hop3

> **Note**: For comprehensive testing documentation, see [Testing Strategy](testing-strategy.md).

## Overview

Hop3 uses a multi-layer testing approach with two complementary systems:

### Test Layers (pytest-based)

1. **Unit Tests** (`tests/a_unit/`) - Individual components in isolation
2. **Integration Tests** (`tests/b_integration/`) - Multiple components within subsystems
3. **System Tests** (`tests/c_system/`) - CLI ↔ Server communication
4. **E2E Tests** (`tests/d_e2e/`) - Full deployments with Docker

### Application Testing (hop3-test-new)

The `hop3-test-new` CLI provides deployment testing for applications:

- **System Testing** - Test Hop3 itself using real `hop3-deploy`
- **Apps Testing** - Test applications against a pre-deployed Hop3 server

## Quick Start

### Run Unit + Integration Tests

```bash
# Fast tests (recommended for development)
make test

# Or using pytest directly
pytest packages/hop3-server/tests/a_unit/ packages/hop3-server/tests/b_integration/
```

### Run System Tests (Docker-based)

```bash
# Test Hop3 system with known-good apps
make test-system

# Or with more apps (CI mode)
uv run hop3-test-new system --mode ci
```

### Run Application Tests

```bash
# Test all apps against pre-built Hop3 image
make test-apps

# Requires building the image first
uv run hop3-test-new build-ready-image
```

## Test Commands Reference

### Makefile Targets

| Command | Description | Duration |
|---------|-------------|----------|
| `make test` | Unit + integration tests | ~30s |
| `make test-system` | System tests (5 fast apps) | ~2min |
| `make test-apps` | All app tests (66 apps) | ~14min |
| `make test-with-coverage` | Tests with coverage report | ~1min |
| `make lint` | Linting and type checking | ~30s |

### hop3-test-new CLI

```bash
# System testing (deploys Hop3 via hop3-deploy)
hop3-test-new system                    # Dev mode (5 fast tests)
hop3-test-new system --mode ci          # CI mode (8 tests, includes medium tier)
hop3-test-new system --deploy-from git  # Deploy from git instead of local
hop3-test-new system --clean            # Clean install first

# Application testing (uses pre-built image)
hop3-test-new apps                      # Test all deployment apps
hop3-test-new apps 010-flask-pip-wsgi   # Test specific app
hop3-test-new apps --category python    # Test by category
hop3-test-new apps -q                   # Quiet mode (no recap)

# Utilities
hop3-test-new build-ready-image         # Build hop3-ready:latest image
hop3-test-new catalog                   # List available tests
```

## Test Organization

### Layer 1: Unit Tests

**Location**: `packages/hop3-server/tests/a_unit/`
**Speed**: < 1 second
**Requirements**: None

```bash
pytest packages/hop3-server/tests/a_unit/ -v
```

### Layer 2: Integration Tests

**Location**: `packages/hop3-server/tests/b_integration/`
**Speed**: ~10 seconds
**Requirements**: None (uses TestClient, in-memory DB)

```bash
pytest packages/hop3-server/tests/b_integration/ -v
```

### Layer 3: System Tests

**Location**: `packages/hop3-server/tests/c_system/`
**Speed**: ~20 seconds
**Requirements**: Docker

```bash
unset HOP3_DEV_HOST
pytest packages/hop3-server/tests/c_system/ -v
```

### Layer 4: E2E Tests

**Location**: `packages/hop3-server/tests/d_e2e/`
**Speed**: 10-20 minutes
**Requirements**: Docker

```bash
pytest packages/hop3-server/tests/d_e2e/ -v
```

## Application Testing with hop3-test-new

### Test Apps Directory

Test applications are located in `apps/test-apps/`:

```
apps/test-apps/
├── 000-static/           # Static website (nginx)
├── 010-flask-pip-wsgi/   # Python Flask with pip
├── 020-nodejs-express/   # Node.js Express
├── 030-golang-gin/       # Go Gin framework
├── 040-sinatra/          # Ruby Sinatra
├── 100-flask-gunicorn-pip/    # Flask with Gunicorn
├── 110-flask-gunicorn-poetry/ # Flask with Poetry
└── 130-golang-minimal/   # Minimal Go app
```

### Test Configuration (test.toml)

Each test app has a `test.toml` file defining its test configuration:

```toml
[test]
name = "010-flask-pip-wsgi"
category = "deployment"
tier = "fast"           # fast, medium, slow, very-slow
priority = "P0"         # P0 (critical), P1, P2

[test.requirements]
targets = ["docker", "remote"]
services = []           # Required services (postgresql, redis, etc.)

[test.metadata]
covers = ["python", "flask", "pip", "uwsgi"]

[deployment]
path = "."
type = "python"

[[validations]]
type = "http"
path = "/"
[validations.expect]
status = 200
contains = "Hello"
```

### Test Modes

| Mode | Tiers | Priority | Use Case |
|------|-------|----------|----------|
| `dev` | fast | P0 | Quick verification (~90s) |
| `ci` | fast, medium | P0 | CI pipelines (~150s) |
| `nightly` | fast, medium, slow | P0, P1 | Nightly builds |
| `release` | all | all | Release validation |

### Test Targets

| Target | Description | Command |
|--------|-------------|---------|
| `docker` | Fresh Hop3 via hop3-deploy | `--target docker` |
| `ready` | Pre-built hop3-ready image | `--target ready` |
| `remote` | Existing remote server | `--target remote --host X` |

## Test Output

### Recap Summary

After tests complete, a recap shows what was tested:

```
============================================================
All 8 tests passed!
Total time: 148.55s
============================================================

Recap:
  ✓ deployment: 8/8 passed
  Tiers: fast=5, medium=3
  Covers: flask, go, golang, gunicorn, minimal, nginx, nodejs, pip, ...
  Avg time per test: 18.6s
```

Use `-q/--quiet` to suppress the recap.

### Diagnostic Logs

Failed tests generate diagnostic logs in `test-logs/`:

```
test-logs/
└── 20260110_155610/
    └── system-hop3-test-docker/
        ├── diagnostics.json
        ├── nginx-error.log
        ├── uwsgi.log
        └── hop3-server.log
```

## Continuous Integration

### GitHub Actions (Planned)

```yaml
# Run on every PR
- make test           # Unit + integration
- make lint           # Linting

# Run on merge to main
- make test-system    # System tests (dev mode)

# Nightly
- hop3-test-new system --mode nightly
```

### SourceHut (Current)

Current CI runs:
- Unit tests
- Integration tests
- Linting and type checking

See: <https://builds.sr.ht/~sfermigier/hop3/>

## Coverage

```bash
# Generate coverage report
pytest --cov=hop3 --cov-report=html

# Open report
open htmlcov/index.html
```

## Troubleshooting

### "Image hop3-ready:latest not found"

Build the ready image first:
```bash
uv run hop3-test-new build-ready-image
```

### Tests Hang

- Check Docker daemon: `docker ps`
- Use verbose mode: `-v -s`
- Check container logs: `docker logs hop3-app-test`

### Import Errors

```bash
uv sync
```

### Docker Issues

```bash
# Clean up containers
docker rm -f hop3-app-test hop3-system-test

# Rebuild images
docker build -f packages/hop3-server/tests/d_e2e/docker/Dockerfile -t hop3-ready:latest .
```

For detailed information, see [Testing Strategy](testing-strategy.md).
