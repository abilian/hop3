# Hop3 Testing Cheat Sheet

Quick reference for developers running tests.

## Quick Commands

| What | Command |
|------|---------|
| **All pytest tests** | `make test` |
| **Full CI suite** | `make test-ci` |
| **System tests (Docker)** | `hop3-test-new system` |
| **App tests (fast)** | `hop3-test-new apps` |
| **Lint & type check** | `make lint` |

## New Test Runner (hop3-test-new)

The new unified test runner provides multiple testing modes.

### Test Modes

```bash
# Developer mode - fast P0 tests only (~2-3 min)
hop3-test-new dev

# CI mode - fast + medium P0 tests (~5-10 min)
hop3-test-new ci

# Nightly mode - all tests (~30+ min)
hop3-test-new nightly
```

### System Testing (Testing Hop3 Itself)

Tests the full Hop3 system by deploying it first, then running tests.

```bash
# Deploy local code to Docker and test
hop3-test-new system

# Deploy from git branch
hop3-test-new system --deploy-from git --branch main

# Clean install (remove existing)
hop3-test-new system --clean

# Use existing deployment (skip deploy)
hop3-test-new system --deploy-from none

# Remote server instead of Docker
hop3-test-new system --target remote --host server.example.com

# Generate HTML report
hop3-test-new system --report html
```

### App Testing (Testing Apps, Not Hop3)

Uses a pre-built Docker image with Hop3 already installed for fast app testing.

```bash
# First, build the ready image (one-time, ~5 min)
hop3-test-new build-ready-image

# Test all apps (~30s per app)
hop3-test-new apps

# Test specific app
hop3-test-new apps 010-flask-pip-wsgi

# Test by category
hop3-test-new apps --category python

# Keep apps deployed after testing
hop3-test-new apps --keep
```

### Listing and Inspecting Tests

```bash
# List all tests
hop3-test-new list

# Filter by category
hop3-test-new list --category deployment

# Filter by tier
hop3-test-new list --tier fast

# Show test details
hop3-test-new show 010-flask-pip-wsgi

# JSON output
hop3-test-new list --format json
```

### Package Validation

For package authors testing their apps against stable Hop3.

```bash
# Validate an app package
hop3-test-new package /path/to/my-app
```

### Building Docker Images

```bash
# Build ready image (pre-installed Hop3)
hop3-test-new build-ready-image
hop3-test-new build-ready-image --tag my-hop3:v1
hop3-test-new build-ready-image --no-cache

# Build test image (for system tests)
hop3-test-new build-test-image
hop3-test-new build-test-image --no-cache
```

## Pytest Tests

### Run by Layer

```bash
# Unit tests only (~330 tests, fast)
uv run pytest packages/hop3-server/tests/a_unit

# Integration tests (~240 tests, medium)
uv run pytest packages/hop3-server/tests/b_integration

# System tests (~15 tests, needs Docker)
uv run pytest packages/hop3-server/tests/c_system

# E2E tests (~15 tests, slow, needs Docker)
uv run pytest packages/hop3-server/tests/d_e2e

# CLI tests
uv run pytest packages/hop3-cli/tests
```

### Run Specific Tests

```bash
# Single file
uv run pytest packages/hop3-server/tests/a_unit/test_app_config.py

# Single test
uv run pytest packages/hop3-server/tests/a_unit/test_app_config.py::test_function_name

# By keyword
uv run pytest -k "backup" packages/hop3-server/tests

# By marker
uv run pytest -m "slow" packages/hop3-server/tests
```

### Useful Flags

```bash
# Verbose output
uv run pytest -v

# Stop on first failure
uv run pytest -x

# Show print statements
uv run pytest -s

# Parallel execution (faster)
uv run pytest -n 4

# Show slowest tests
uv run pytest --durations=10

# Coverage report
uv run pytest --cov=hop3 --cov-report=term-missing
```

## Common Workflows

### Before Committing

```bash
make lint      # Check formatting and types
make test      # Run all pytest tests
```

### Quick Validation (Developer)

```bash
# Fast tests against Docker
hop3-test-new dev
```

### Full Validation (CI)

```bash
# Full CI suite
make test-ci

# Or manually
hop3-test-new ci --report html
```

### Debug a Failing Test

```bash
# Run with verbose output
uv run pytest -v -s path/to/test.py::test_name

# Keep target running for inspection
hop3-test-new apps --keep 010-flask-pip-wsgi

# Run system tests and keep target
hop3-test-new system --keep

# Generate HTML report for analysis
hop3-test-new system --report html
```

### Test Coverage

```bash
make test-with-coverage

# HTML report
uv run pytest --cov=hop3 --cov-report=html
open htmlcov/index.html
```

## Test Directory Structure

```
packages/hop3-server/tests/
├── a_unit/          # Fast, isolated tests
├── b_integration/   # Component interaction tests
├── c_system/        # Docker-based system tests
└── d_e2e/           # Full deployment tests (legacy)

packages/hop3-testing/    # Test framework
├── src/hop3_testing/
│   ├── catalog/         # Test catalog (test.toml support)
│   ├── cli/             # CLI commands
│   ├── runners/         # Test runners
│   ├── results/         # Result storage and reporting
│   ├── selector/        # Test selection logic
│   └── targets/         # Deployment targets

apps/test-apps/          # Test applications
├── 000-static/
├── 010-flask-pip-wsgi/
├── 020-nodejs-express/
└── ...
```

## Test Configuration (test.toml)

Tests can be configured with `test.toml` files:

```toml
[test]
name = "010-flask-pip-wsgi"
category = "deployment"
tier = "fast"
priority = "P0"
description = "Basic Flask app with pip and WSGI"

[test.requirements]
targets = ["docker", "remote"]
services = []

[[test.validations]]
type = "http"
path = "/"
expect.status = 200
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `HOP3_DEV_HOST` | SSH target for deployment |
| `HOP3_TEST_HOST` | SSH target for app tests |
| `HOP3_TEST_SSH_KEY` | SSH key for remote tests |
| `HOP3_UNSAFE=true` | Disable auth in Docker tests |

## Troubleshooting

### Docker Tests Fail

```bash
# Check if container is running
docker ps -a | grep hop3

# View container logs
docker logs hop3-test

# Rebuild test image
hop3-test-new build-test-image --no-cache
```

### App Tests Fail (Ready Image)

```bash
# Rebuild ready image
hop3-test-new build-ready-image --no-cache

# Test with verbose output
hop3-test-new apps -v 010-flask-pip-wsgi

# Check HTML report
hop3-test-new apps --report html
```

### System Tests Timeout

```bash
# Check deployment status
hop3-test-new system --deploy-from none --keep

# View diagnostic logs
ls test-logs/
```

### Remote Tests Fail

```bash
# Verify SSH connection
ssh hop3@$HOP3_TEST_HOST "hop3 --version"

# Check server status
ssh root@$HOP3_TEST_HOST "systemctl status hop3-server"
```

## Target Types

| Target | Use Case | Speed |
|--------|----------|-------|
| `docker` | System tests with fresh deploy | Slow (~5 min startup) |
| `ready` | App tests with pre-built image | Fast (~30s startup) |
| `remote` | Tests against real servers | Variable |

### When to Use Each

- **`hop3-test-new system`**: Testing Hop3 changes (deploys Hop3 first)
- **`hop3-test-new apps`**: Testing app configurations (uses pre-built image)
- **`hop3-test-new dev/ci`**: Mode-based selection for CI pipelines
