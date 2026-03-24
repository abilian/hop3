# Hop3 Test Status

**Last Updated**: 2026-02-17

## Test Summary

| Layer | Status |
|-------|--------|
| Unit (`a_unit/`) | Passing |
| Integration (`b_integration/`) | Passing |
| System (`c_system/`) | Passing |
| E2E (`d_e2e/`) | 9 apps passing, 1 skipped |

## Test Structure

```
packages/hop3-server/tests/
├── a_unit/              # Layer 1: Unit Tests
├── b_integration/       # Layer 2: Integration Tests
├── c_system/            # Layer 3: System Tests
└── d_e2e/               # Layer 4: End-to-End Tests
```

## Test Pyramid

### Layer 1: Unit Tests (`a_unit/`)

**Purpose**: Test individual functions and classes in isolation

**Status**: Passing
- Fast execution (< 1 second total)
- No external dependencies
- Good coverage of commands, ORM, plugins

**Coverage**:
- Commands (admin, auth, config, services, git hooks)
- Core functionality (app config, hop3 config)
- ORM models
- Plugin implementations
- uWSGI settings

### Layer 2: Integration Tests (`b_integration/`)

**Purpose**: Test multiple components working together

**Status**: Passing
- Medium execution time (~10 seconds)
- Uses real database (in-memory SQLite)
- Uses Litestar TestClient

**Coverage**:
- Auth commands (register, login, whoami, logout)
- RPC endpoint security (token validation, tampering, injection)
- Command authentication and authorization
- Dashboard views (app management, service management)
- Service credential management

### Layer 3: System Tests (`c_system/`)

**Purpose**: Test full CLI-server communication in Docker

**Status**: Passing
- Requires Docker
- Uses `HOP3_UNSAFE=true` for auth bypass in tests
- Tests real HTTP communication

**Coverage**:
- CLI availability and basic functionality
- Dashboard app creation/management
- Authentication flows

### Layer 4: E2E Tests (`d_e2e/`)

**Purpose**: Test complete deployment workflows

**Status**: 7 passing, 1 skipped
- Slow execution (10-20 minutes)
- Full Hop3 stack in Docker
- Real application deployments

**Test Apps**:
| App | Status |
|-----|--------|
| 000-static | Passing |
| 010-flask-pip-wsgi | Passing |
| 020-nodejs-express | Passing |
| 030-golang-gin | Skipped (under investigation) |
| 030-rack | Passing |
| 040-sinatra | Passing |
| 050-clojure | Passing |
| 100-flask-gunicorn-pip | Passing |
| 120-flask-pip-alt | Passing |
| 130-golang-minimal | Passing |

## Test Execution Times

| Layer | Time | When to Run |
|-------|------|-------------|
| Unit | < 5s | During development |
| Integration | ~10s | Before commits |
| System | ~30s | Before push |
| E2E | 10-20 min | CI/CD, before release |

## Quick Commands

```bash
# All fast tests
make test

# Full CI suite
make test-ci

# Individual layers
uv run pytest packages/hop3-server/tests/a_unit
uv run pytest packages/hop3-server/tests/b_integration
uv run pytest packages/hop3-server/tests/c_system
uv run pytest packages/hop3-server/tests/d_e2e
```

## Known Issues

1. **Go Gin app** (`030-golang-gin`): Skipped, under investigation.

2. **MySQL SSL with Rails**: Deferred. Demo44 (Rails) switched to PostgreSQL.

## Recent Improvements (2026)

- **Health check system** (2026-02-17): Plugin-based health checks for MySQL, PostgreSQL, Redis
- **`hop3 system:check` command** (2026-02-17): Comprehensive server health validation
- **ENV file ORM storage** (2026-02-16): Fixed HOST_NAME not stored during deployment
- **PYTHONPATH for src-layout** (2026-02-16): Auto-detect src/ directory for Python apps
- **Improved error messages** (2026-02-16): HTTP test failures now include response details
