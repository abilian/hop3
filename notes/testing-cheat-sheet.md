# Hop3 Testing Cheat Sheet

Quick reference for developers running tests.

## Prerequisites

```bash
# Set target server for SSH-based tests
export HOP3_DEV_HOST=your-server.example.com

# Or use Docker (no server needed)
make deploy-docker
```

## Quick Commands

| What | Command |
|------|---------|
| **All pytest tests** | `make test` |
| **Full CI suite** | `make test-ci` |
| **Demos only (Docker)** | `make test-demos-docker` |
| **Demos only (SSH)** | `make test-demos-ssh` |
| **Lint & type check** | `make lint` |

## Pytest Tests

### Run by Layer

```bash
# Unit tests only (~330 tests, fast)
uv run pytest packages/hop3-server/tests/a_unit

# Integration tests (~240 tests, medium)
uv run pytest packages/hop3-server/tests/b_integration

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

## Demo Tests

Demos test real application deployments in `apps/test-apps/`.

### Docker Backend (no server required)

```bash
# All demos
make test-demos-docker

# Verbose
python demos/demo.py --backend docker

# Specific demo
python demos/demo.py --backend docker --only 010-flask-pip-wsgi
```

### SSH Backend (requires HOP3_DEV_HOST)

```bash
# All demos
make test-demos-ssh

# Verbose
python demos/demo.py --host $HOP3_DEV_HOST

# Specific demo
python demos/demo.py --host $HOP3_DEV_HOST --only 010-flask-pip-wsgi
```

### Demo Flags

```bash
--only NAME      # Run single demo
--skip NAME      # Skip specific demo
--quiet          # Less output
--no-cleanup     # Keep apps after test (for debugging)
```

## Tutorial Tests

```bash
# Run all tutorials (SSH only)
make test-tutorials-ssh
# or
./scripts/run-all-tutorials.sh
```

## Deployment for Testing

```bash
# Deploy to SSH server (from local code)
make deploy

# Deploy to Docker container
make deploy-docker

# Deploy with extra options
uv run hop3-deploy --help
```

## Installer Tests

```bash
# Build installers first
make build-installers

# Test in Docker (Ubuntu)
make test-installer

# More options
uv run hop3-install test --help
uv run hop3-install test docker --distro debian
uv run hop3-install test docker --all
uv run hop3-install test ssh --host $HOP3_TEST_HOST
```

## Common Workflows

### Before Committing

```bash
make lint      # Check formatting and types
make test      # Run all pytest tests
```

### Full Validation

```bash
make test-ci   # Everything: pytest + demos + tutorials
```

### Debug a Failing Test

```bash
# Run with verbose output
uv run pytest -v -s path/to/test.py::test_name

# Keep Docker container running for inspection
python demos/demo.py --backend docker --only failing-demo --no-cleanup

# Check E2E logs
docker logs hop3-e2e-test
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
├── c_system/        # (mostly unused)
└── d_e2e/           # Full deployment tests

apps/test-apps/      # Demo applications
├── 000-static/
├── 010-flask-pip-wsgi/
├── 020-nodejs-express/
└── ...
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `HOP3_DEV_HOST` | SSH target for demos/tutorials |
| `HOP3_TEST_HOST` | SSH target for installer tests |
| `HOP3_UNSAFE=true` | Disable auth in Docker tests |

## Troubleshooting

### Docker Tests Fail

```bash
# Check if container is running
docker ps -a | grep hop3

# View container logs
docker logs hop3-e2e-test

# Restart container
make deploy-docker
```

### E2E Tests Timeout

```bash
# Increase timeout
uv run pytest --timeout=300 packages/hop3-server/tests/d_e2e
```

### Demo Fails

```bash
# Run single demo with output
python demos/demo.py --backend docker --only 010-flask-pip-wsgi

# Keep container for debugging
python demos/demo.py --backend docker --only 010-flask-pip-wsgi --no-cleanup

# SSH into container
docker exec -it hop3-e2e-test bash
```
