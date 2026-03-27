# Hop3 Testing Cheat Sheet

Quick reference for developers running tests.

## Quick Commands

| What | Command |
|------|---------|
| **All pytest tests** | `make test` |
| **Full CI suite** | `make test-ci` |
| **System tests (Docker)** | `hop3-test system --docker` |
| **App tests (fast)** | `hop3-test apps` |
| **Lint & type check** | `make lint` |

## hop3-test CLI

The unified test runner for Hop3 deployment testing.

### System Testing (Testing Hop3 Itself)

Deploys Hop3 using `hop3-deploy`, then runs tests against it.

```bash
# Deploy local code to Docker and test
hop3-test system --docker

# Deploy from git branch
hop3-test system --docker --deploy-from git --branch main

# Deploy from PyPI
hop3-test system --docker --deploy-from pypi

# Clean install (remove existing)
hop3-test system --docker --clean

# Reuse existing deployment (skip deploy)
hop3-test system --docker --reuse
# Or equivalently:
hop3-test system --docker --deploy-from none

# Remote server via SSH
hop3-test system --ssh --host server.example.com

# SSH using HOP3_TEST_HOST env var
export HOP3_TEST_HOST=server.example.com
hop3-test system --ssh

# Test mode: dev (fast) or ci (more thorough)
hop3-test system --docker --mode ci

# Keep target running after tests
hop3-test system --docker --keep

# Generate HTML report
hop3-test system --docker --report html
```

#### Deploy-from Options

| Option | Description |
|--------|-------------|
| `--deploy-from local` | Upload and install local code (default) |
| `--deploy-from git` | Clone and install from git branch |
| `--deploy-from pypi` | Install from PyPI |
| `--deploy-from none` | Skip deployment, use existing |
| `--reuse` | Alias for `--deploy-from none` |

### App Testing (Testing Apps, Not Hop3)

Uses a pre-built Docker image with Hop3 already installed.

```bash
# First, build the ready image (one-time)
hop3-test build-ready-image

# Test all apps
hop3-test apps

# Test specific app
hop3-test apps 010-flask-pip-wsgi

# Test by category
hop3-test apps --category python

# Keep apps deployed after testing
hop3-test apps --keep

# Against remote server
hop3-test apps --target remote --host server.example.com
```

### Listing and Inspecting Tests

```bash
# List all tests
hop3-test list

# Filter by category
hop3-test list --category deployment

# Filter by tier
hop3-test list --tier fast

# Show test details
hop3-test show 010-flask-pip-wsgi
```

### Package Validation

For package authors testing their apps against stable Hop3.

```bash
# Validate an app package
hop3-test package /path/to/my-app
```

### Building Docker Images

```bash
# Build ready image (pre-installed Hop3)
hop3-test build-ready-image
hop3-test build-ready-image --tag my-hop3:v1
hop3-test build-ready-image --no-cache

# Build test image (for system tests)
hop3-test build-test-image
hop3-test build-test-image --no-cache
```

### Quick Modes

```bash
# Developer mode (fast P0 tests only)
hop3-test dev

# CI mode (fast + medium P0 tests)
hop3-test ci

# Nightly mode (all tiers, all priorities)
hop3-test nightly
```

## Pytest Tests

### Run by Layer

```bash
# Unit tests (~361 tests, fast)
uv run pytest packages/hop3-server/tests/a_unit

# Integration tests (~247 tests, medium)
uv run pytest packages/hop3-server/tests/b_integration

# System tests (~13 tests, needs Docker)
uv run pytest packages/hop3-server/tests/c_system

# E2E tests (~17 tests, slow, needs Docker)
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
hop3-test system --docker --mode dev
```

### Full Validation (CI)

```bash
# Full CI suite
make test-ci

# Or manually
hop3-test system --docker --mode ci --report html
```

### Debug a Failing Test

```bash
# Run with verbose output
uv run pytest -v -s path/to/test.py::test_name

# Keep target running for inspection
hop3-test apps --keep 010-flask-pip-wsgi

# Run system tests and keep target
hop3-test system --docker --keep

# Reuse container for fast iteration
hop3-test system --docker --reuse --keep

# Generate HTML report for analysis
hop3-test system --docker --report html
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
└── d_e2e/           # Full deployment tests

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
├── 030-golang-gin/       # Skipped
├── 030-rack/
├── 040-sinatra/
├── 050-clojure/
├── 100-flask-gunicorn-pip/
├── 120-flask-pip-alt/
└── 130-golang-minimal/

apps/nix-apps/           # Nix-based test applications
└── flask-hello/
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
| `HOP3_TEST_HOST` | SSH target for `--ssh` without `--host` |
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
hop3-test build-test-image --no-cache
```

### App Tests Fail (Ready Image)

```bash
# Rebuild ready image
hop3-test build-ready-image --no-cache

# Test with verbose output
hop3-test apps -v 010-flask-pip-wsgi

# Check HTML report
hop3-test apps --report html
```

### System Tests Timeout

```bash
# Reuse existing container to debug
hop3-test system --docker --reuse --keep

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
| `--docker` | System tests with fresh deploy | Slow (~5 min startup) |
| `ready` | App tests with pre-built image | Fast (~30s startup) |
| `--ssh` | Tests against real servers | Variable |

### When to Use Each

- **`hop3-test system --docker`**: Testing Hop3 changes (deploys Hop3 first)
- **`hop3-test system --docker --reuse`**: Fast iteration on existing container
- **`hop3-test system --ssh --host X`**: Testing against remote servers
- **`hop3-test apps`**: Testing app configurations (uses pre-built image)
