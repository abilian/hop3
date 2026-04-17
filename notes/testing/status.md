# Hop3 Test Status

**Last Updated**: 2026-04-09

## Test Summary

| Layer | Status | Count |
|-------|--------|-------|
| Unit (`a_unit/`) | Passing | 599 tests (6 skipped) |
| Integration (`b_integration/`) | Passing | 245+ tests |
| System (`c_system/`) | Passing | Full CLI-server in Docker |
| E2E (`d_e2e/`) | See app suites below | 4 suites, 118 apps total |

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

**Status**: 599 passing, 6 skipped — ~7s execution

**Coverage**:
- Commands (admin, auth, config, services, git hooks, nix:eject)
- Core functionality (app config, hop3 config, protocols)
- ORM models
- Plugin implementations (nix-gen: 119 tests across 7 test files)
- uWSGI settings
- Shell command execution

### Layer 2: Integration Tests (`b_integration/`)

**Status**: 245+ passing — ~10s execution

**Coverage**:
- Auth commands (register, login, whoami, logout)
- RPC endpoint security (token validation, tampering, injection)
- Dashboard views (app management, service management)
- Service credential management

### Layer 3: System Tests (`c_system/`)

**Status**: Passing — ~30s, requires Docker

### Layer 4: E2E / Deployment Tests

Run via `hop3-test system` against Docker or SSH targets.

#### App Suites

| Suite | Location | Count | Last Status |
|-------|----------|-------|-------------|
| Procfile test apps | `apps/test-apps-procfile/` | 8 | All passing |
| Nix test apps | `apps/test-apps-nix/` | 10 | Mostly passing |
| Native real apps | `apps/real-apps-native/` | 28 | All passing |
| Nix hand-crafted | `apps/real-apps-nix/` | 22 | 20-22 passing |
| Nix template-gen | `apps/real-apps-nix-gen/` | 20 | 14-20 passing |
| Docker real apps | `apps/real-apps-docker/` | 30 | ~20 passing |

#### Test Harness Features (hop3-test)

- `--with` flag filters by required services (nix, mysql, postgres, redis, docker)
- Direct port HTTP testing (bypasses nginx)
- SSH-based curl for remote targets (firewall-safe)
- Nginx-based testing for static/no-port apps
- 10-minute deploy timeout (prevents silent hangs)
- Real-time streaming of deploy output
- Response body in error messages for diagnosis

#### Docker App Known Issues

Several Docker apps have infrastructure issues unrelated to Hop3:
- MySQL apps may fail if `host.docker.internal` doesn't resolve correctly
- Some apps need long startup times (formbricks, mastodon, xwiki)
- Monica: Docker build is slow (npm + webpack > 10 min)

## Test Execution Times

| Layer | Time | When to Run |
|-------|------|-------------|
| Unit | ~7s | During development |
| Integration | ~10s | Before commits |
| System | ~30s | Before push |
| E2E (one suite) | 10-60 min | CI/CD, before release |

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

# Deployment tests (requires server)
hop3-test system --docker --clean --with nix apps/test-apps-*
hop3-test system --ssh --host $HOP3_DEV_HOST --clean --with all apps/real-apps-*
```

## Recent Improvements (2026-04)

- **Test harness hardening** (W15): Deploy timeout, service filtering, body in errors
- **Static site support** (W15): Fixed absolute path handling, nginx SSH testing
- **Docker test.toml** (W15): All 30 Docker apps now have test definitions
- **NixEjectCmd tests** (W15): 5 tests for nix:eject command (previously zero coverage)
- **Nix gen tests** (W14): 119 unit tests across 7 test files for template generator
- **Direct port testing** (W14): HTTP testing via app port, bypassing nginx
- **SSH curl testing** (W14): Test remote apps via curl on the server
