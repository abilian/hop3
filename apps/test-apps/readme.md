# Test Apps for Hop3

Minimal "Hello World" applications covering core language toolchains. Used for automated testing of the Hop3 platform.

## Applications

| App | Stack | Description |
|-----|-------|-------------|
| `000-static` | Static | HTML/CSS served by nginx |
| `010-flask-pip-wsgi` | Python | Flask with pip, uWSGI |
| `020-nodejs-express` | Node.js | Express.js |
| `030-golang-gin` | Go | Gin framework |
| `040-sinatra` | Ruby | Sinatra with Puma |
| `100-flask-gunicorn-pip` | Python | Flask with Gunicorn |
| `110-flask-gunicorn-poetry` | Python | Flask with Poetry |
| `130-golang-minimal` | Go | Minimal Go HTTP server |

## Running Tests

### Using hop3-test (recommended)

```bash
# List available tests
uv run hop3-test list

# Run all app tests (requires HOP3_DEV_HOST or Docker)
uv run hop3-test apps

# Run developer tests (fast, P0 only)
uv run hop3-test dev

# Run CI tests (fast+medium, P0)
uv run hop3-test ci
```

### Using pytest directly

```bash
# System tests (Docker-based)
uv run pytest packages/hop3-server/tests/c_system/ -v

# E2E tests (full deployment)
uv run pytest packages/hop3-server/tests/d_e2e/ -v
```

### Using Makefile

```bash
make test-apps      # Test apps against pre-built image
make test-system    # Run system tests
```

## Test Configuration

Each app includes a `test.toml` file defining:

```toml
[test]
name = "010-flask-pip-wsgi"
category = "deployment"
tier = "fast"              # fast, medium, slow
priority = "P0"            # P0 (critical), P1, P2
description = "..."

[test.requirements]
targets = ["docker", "remote"]
services = []              # e.g., ["postgresql", "redis"]

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

## Prerequisites

- **Docker**: For local testing (`hop3-test` builds containers automatically)
- **Remote server**: Set `HOP3_DEV_HOST` for SSH-based testing

```bash
# Docker-based testing
uv run hop3-test apps

# Remote server testing
export HOP3_DEV_HOST=your-server.example.com
uv run hop3-test apps
```
