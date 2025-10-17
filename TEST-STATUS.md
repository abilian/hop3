# Hop3 - Test Hierarchy & Strategy

**Date**: 2025-10-17

### Current Test Structure

```
packages/hop3-server/tests/
├── a_unit/              # Layer 1: Unit Tests
├── b_integration/       # Layer 2: Integration Tests
├── c_system/            # Layer 3: System Tests
└── d_e2e/              # Layer 4: End-to-End Tests
```

### Test Pyramid (Bottom to Top)

#### Layer 1: Unit Tests (`a_unit/`)
**Purpose**: Test individual functions and classes in isolation

**Current Status**: ✅ Working
- Fast execution (< 1 second)
- No external dependencies
- Mock databases, file systems, external services
- Test business logic in isolation

**Coverage**:
- Commands (admin, auth, config, help, git hooks, services)
- Core functionality (app config, hop3 config)
- Individual components

**What's Working**:
- All unit tests pass
- Good coverage of command logic
- Proper mocking and isolation

**What's Missing**:
- Some newer features may lack unit test coverage
- Could expand coverage of utility modules

#### Layer 2: Integration Tests (`b_integration/`)
**Purpose**: Test multiple components working together within subsystems

**Current Status**: ✅ Working
- Medium execution time (~10 seconds)
- Uses real database (in-memory SQLite)
- No external network dependencies
- Tests component interactions

**Coverage**:
- Auth commands end-to-end (register, login, whoami, logout)
- RPC endpoint security (token validation, tampering, injection)
- Command authentication and authorization
- Database operations

**What's Working**:
- 105+ tests passing
- Comprehensive auth command testing
- Excellent security testing (token tampering, injection attacks)
- RPC authentication flow

**What's Missing**:
- Deployment command integration tests
- Full app lifecycle integration tests
- Database migration testing

**Known Limitations**:
- 2 tests skipped due to Starlette test client limitations with AuthenticationMiddleware

#### Layer 3: System Tests (`c_system/`)
**Purpose**: Test the full application with real dependencies in Docker

**Current Status**: ✅ Recently Fixed (converted to Docker)
- Medium execution time (~20 seconds after image build)
- Uses Docker containers (hop3-e2e:test image)
- Real hop3-server running in container
- HTTP-based CLI communication

**Coverage**:
- CLI availability and basic functionality
- Authentication commands (register, login)
- App deployment via tarball
- App lifecycle (deploy, list, destroy)
- Git hook deployment

**What's Working**:
- 9 tests passing with Docker
- Isolated test environment
- Consistent with d_e2e infrastructure
- No dependency on remote servers

**What's Missing**:
- Full deployment workflow tests
- Process management tests
- Environment variable management tests
- Service attachment tests (PostgreSQL, Redis)

**Note**: 5 tests are "remote server diagnostics" that only run when `HOP3_DEV_HOST` is set - these are for testing actual remote deployments, not part of standard test suite.

#### Layer 4: E2E Tests (`d_e2e/`)
**Purpose**: Test complete workflows in production-like Docker environment

**Current Status**: ⚠️ Partially Working
- Slow execution time (2-10 minutes, includes image build)
- Docker containers with supervisor (not systemd)
- Full hop3 stack (server, SSH, HTTP, apps)
- Real deployment workflows

**Coverage**:
- Python Flask app deployment
- Full deployment lifecycle
- HTTP endpoint verification
- Git hook deployment
- Security tests

**What's Working**:
- Docker infrastructure (image builds, containers start)
- Basic Flask app deployment
- Container lifecycle management

**What's NOT Working** (from background processes):
- Test `test_deploy_simple_flask_app` appears to be hanging/failing
- Need to investigate background bash outputs to see what's failing

**What's Missing**:
- Multi-process app tests (web + worker)
- Different app types (Node.js, Go, etc.)
- Environment variable injection tests
- Domain/routing tests
- SSL/HTTPS tests
- Performance/load tests

### Test Execution Times

| Layer | Time | Use Case |
|-------|------|----------|
| Unit | < 1s | During development (every save) |
| Integration | ~10s | Before commits |
| System | ~20s | Before push |
| E2E | 2-10min | CI/CD, before release |

### What's Needed

1. **Expand c_system coverage**:
   - Add tests for all deployment scenarios
   - Test process management (start/stop/restart)
   - Test config management (set/unset env vars)
   - Test service integration (PostgreSQL, Redis)

2. **Fix and expand d_e2e tests**:
   - Debug failing Flask deployment test
   - Add multi-process app tests
   - Add different runtime tests (Node.js, etc.)
   - Add scaling tests

3. **Add missing test types**:
   - Performance tests (load testing, resource usage)
   - Chaos tests (process crashes, network failures)
   - Security tests (privilege escalation, container escape)
   - Upgrade/migration tests

4. **CI/CD Integration**:
   - Ensure tests run in correct order (fast → slow)
   - Fail fast on unit/integration failures
   - Parallel test execution where possible
   - Test result reporting and coverage tracking

### Next Steps (Testing)

**Immediate**:
1. 🔄 Debug d_e2e Flask deployment test (check background processes)
2. Add more c_system tests for deployment scenarios

**Short Term**:
1. Expand c_system test coverage (process management, config, services)
2. Fix all d_e2e tests
3. Add multi-process app e2e tests
4. Document testing strategy in docs/

**Medium Term**:
1. Add performance tests
2. Add chaos engineering tests
3. Improve test execution speed
4. Set up proper CI/CD with test stages
