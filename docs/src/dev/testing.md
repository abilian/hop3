# Testing Hop3

> **Note**: For comprehensive testing documentation, see [Testing Strategy](testing-strategy.md).

## Overview

Hop3 uses a four-layer testing approach:

1. **Unit Tests** (`tests/a_unit/`) - Individual components in isolation
2. **Integration Tests** (`tests/b_integration/`) - Multiple components within subsystems
3. **System Tests** (`tests/c_system/`) - CLI ↔ Server communication
4. **E2E Tests** (`tests/d_e2e/`) - Full deployments with Docker

## Quick Start

### Run All Tests (Unit + Integration)

```bash
# Using pytest
pytest

# Using make
make test

# Using just
just test
```

### Run Specific Test Layers

```bash
# Unit tests only (fast, ~10 seconds)
pytest packages/hop3-server/tests/a_unit/

# Integration tests only (~1 minute)
pytest packages/hop3-server/tests/b_integration/

# System integration tests (requires running server, ~5 minutes)
pytest packages/hop3-server/tests/c_system/

# Full E2E tests (requires Docker, ~20 minutes)
pytest packages/hop3-server/tests/d_e2e/
```

## Test Organization

### Layer 1: Unit Tests (`tests/a_unit/`)
**Scope**: Individual components in isolation
**Speed**: Very fast (< 1s total)
**Requirements**: None

```bash
pytest packages/hop3-server/tests/a_unit/ -v
```

### Layer 2: Integration Tests (`tests/b_integration/`)
**Scope**: Multiple components within subsystem
**Speed**: Fast (< 1 minute)
**Requirements**: None (uses TestClient, in-memory DB)

```bash
pytest packages/hop3-server/tests/b_integration/ -v
```

Includes:
- RPC security tests
- Authentication middleware tests
- Multi-component interaction tests

### Layer 3: System Integration Tests (`tests/c_system/`)
**Scope**: CLI ↔ Server RPC communication via Docker
**Speed**: Medium (~20 seconds after initial image build)
**Requirements**: Docker

```bash
# Tests automatically start Docker container with hop3-server
# Ensure HOP3_DEV_HOST is NOT set
unset HOP3_DEV_HOST
pytest packages/hop3-server/tests/c_system/ -v
```

**Docker-based Testing** (default):
- Tests automatically build and use `hop3-e2e:test` Docker image
- Fresh container per test session
- Isolated, reproducible environment
- No manual server management needed

**Remote Server Diagnostics** (optional):
Some tests in `test_connection.py` can optionally test against a remote server:
```bash
# Only for remote server diagnostics (not regular testing)
export HOP3_DEV_HOST=hop3@test-server.example.com
pytest packages/hop3-server/tests/c_system/test_connection.py -v
```

⚠️ **Important**: For normal development and CI/CD, always ensure `HOP3_DEV_HOST` is **not set**.

### Layer 4: Full E2E Tests (`tests/d_e2e/`)
**Scope**: Complete system with real deployments
**Speed**: Slow (10-20 minutes)
**Requirements**: Docker

```bash
# Install Docker requirements
pip install -r packages/hop3-server/tests/d_e2e/requirements.txt

# Run E2E tests
pytest packages/hop3-server/tests/d_e2e/ -v
```

Includes:
- Python Flask/Django deployments
- Node.js deployments (future)
- Ruby deployments (future)
- Database service tests (future)

## Legacy E2E Testing (hop3-testing)

The `packages/hop3-testing/` package provides a legacy E2E test framework using the `hop3-test` command. This is still used for manual testing but will be replaced by the Docker-based E2E tests in `tests/d_e2e/`.

```bash
# Legacy E2E tests (requires remote server)
export HOP3_DEV_HOST=hop3@your-server.com
make test-e2e
```

## Continuous Integration

### GitHub Actions (Future)

Planned GitHub Actions workflow:
- **Unit + Integration**: Run on every push
- **System Tests**: Run with local server in background
- **E2E Tests**: Run on schedule or manual trigger

### SourceHut (Current)

We are using `SourceHut` for our CI/CD pipeline. The configuration is stored in the `.builds` directory.

See: <https://builds.sr.ht/~sfermigier/hop3/> for the current build status.

Currently running:
- Unit tests
- Integration tests
- Linting and type checking

E2E tests are not yet automated in CI.

## Coverage

View test coverage:
```bash
# Generate coverage report
pytest --cov=hop3 --cov-report=html

# Open in browser
open htmlcov/index.html
```

Current coverage targets:
- Overall: > 75%
- Core modules: > 85%

## Writing Tests

See [Testing Strategy](testing-strategy.md) for:
- Best practices
- Test naming conventions
- Fixture guidelines
- Parametrized tests
- Common patterns

## Troubleshooting

### Tests Hang
- Check if server is running (for system tests)
- Check Docker daemon (for E2E tests)
- Use `-v -s` flags to see progress

### Import Errors
- Ensure packages are installed: `uv sync`
- Check PYTHONPATH if running tests directly

### Database Errors
- Unit/integration tests use in-memory SQLite
- System/E2E tests need PostgreSQL

For more details, see the comprehensive [Testing Strategy](testing-strategy.md) document.
