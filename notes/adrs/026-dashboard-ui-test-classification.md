# ADR 026: Dashboard UI Test Classification

- **Status**: Superseded
- **Type**: Guideline
- **Created**: 2025-11-20
- **Superseded-By**: [ADR 043](./043-unified-testing-architecture.md)
- **Related-ADRs**: [020](./020-pluggable-architecture.md), [024](./024-backup-restore-system.md), [043](./043-unified-testing-architecture.md)

## Superseding Context

This guideline relied on a four-layer test pyramid (`a_unit`/`b_integration`/`c_system`/`d_e2e`) and classified tests by whether their dependencies were real or mocked. [ADR 043](043-unified-testing-architecture.md) replaces that pyramid with three layers (`a_unit`/`b_integration`/`c_e2e`) and dissolves `c_system`. [ADR 043](./043-unified-testing-architecture.md) classifies tests by whether they need Docker, root, or host-mutation rather than by real-vs-mocked dependencies. Under that rule the dashboard file-system tests are hermetic (they run a real `App.create()` in `tmp_path` with no root and no Docker) and therefore belong in `b_integration`, reversing the placement decision recorded here.

## Introduction

This ADR addresses the question of how to properly classify and implement tests for the Hop3 dashboard web UI, specifically focusing on where the boundary lies between integration tests and system tests when testing web application features.

## Summary

Dashboard UI tests that involve file system operations belong in system tests (`c_system/`) with a real `App.create()` implementation, rather than as integration tests with mocked file operations.

## Context and Goals

### Context

The dashboard app creation feature (`/dashboard/apps/new`) is exercised by tests that verify:
- Form rendering and validation
- App creation with database persistence

A mocked-integration arrangement (`packages/hop3-server/tests/b_integration/test_dashboard_app_create.py`) takes this shape:
```python
@pytest.fixture
def test_client(tmp_path: Path, monkeypatch):
    # Patches HOP3_ROOT for database location
    monkeypatch.setattr(hop3.config, "HOP3_ROOT", tmp_path)

    # Mocks App.create() to avoid real file system operations
    def mock_app_create(self):
        app_path = tmp_path / "apps" / self.name
        app_path.mkdir(exist_ok=True)
        # Creates subdirectories...

    monkeypatch.setattr(App, "create", mock_app_create)
    monkeypatch.setattr(SessionAuthBackend, "authenticate", mock_authenticate)
```

**What this arrangement verifies:**
- ✅ Real Starlette HTTP request/response cycle
- ✅ Real route handlers (`@router.get`, `@router.post`)
- ✅ Real Jinja2 template rendering
- ✅ Real SQLAlchemy database operations (SQLite in tmp_path)
- ✅ Real form validation logic
- ❌ **Mocked** `App.create()` method (file system operations)
- ❌ **Mocked** authentication

### Goals

1. **Maintain fast feedback loops** - Tests should run quickly during development
2. **Ensure adequate coverage** - Critical business logic must be tested with real implementations
3. **Follow testing pyramid principles** - Clear separation between test layers
4. **Avoid test brittleness** - Tests shouldn't be overly complex or fragile
5. **Document clear guidelines** - Future developers should know where to place tests

## Tenets

From Hop3's testing strategy (`docs/src/dev/testing-strategy.md`):

1. **Unit Tests** (a_unit/) - Individual functions/classes in isolation, mock all dependencies
2. **Integration Tests** (b_integration/) - Multiple components within subsystems, **without external dependencies**
3. **System Tests** (c_system/) - Full application **with real dependencies** (databases, file systems)
4. **E2E Tests** (d_e2e/) - Complete workflows in Docker containers

Key principle from the documentation:
> **Integration Tests**: "Test multiple components working together within subsystems. Uses real database (in-memory SQLite). No external network dependencies."

The question: **Is the file system an "external dependency" or part of the subsystem under test?**

## Decision

**DECISION: Option 2 - System Tests**

Dashboard UI tests for the app creation feature live in `c_system/` and use the real `App.create()` implementation without mocks, rather than in `b_integration/` with `App.create()` mocked.

**Rationale:**
1. `App.create()` is core business logic that creates the application's directory structure
2. The performance overhead is negligible
3. Removes mock maintenance burden - tests use real code
4. Better bug detection - catches issues a mock would hide (e.g. a `log` vs `logs` directory-name discrepancy)
5. Clearer semantics - "system test" clearly means "full stack with real dependencies"

**What's tested:**
- Real HTTP request/response cycle (Starlette)
- Real route handlers and form validation
- Real database operations (SQLAlchemy + SQLite)
- Real template rendering (Jinja2)
- **Real file system operations** (App.create() directory creation)
- Only authentication is mocked for test convenience

## Option 1: Integration Tests with Mocks

**Decision**: Dashboard UI tests remain in `b_integration/` with `App.create()` mocked.

**Rationale:**
- The file system is considered an "external dependency" like network I/O
- Integration tests focus on web framework + database integration
- File system operations are implementation details of the domain layer
- Faster test execution (no real file operations)

**Test Structure:**
```python
# Location: packages/hop3-server/tests/b_integration/test_dashboard_app_create.py

@pytest.fixture
def test_client(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(hop3.config, "HOP3_ROOT", tmp_path)
    monkeypatch.setattr(App, "create", mock_app_create)  # MOCKED
    # Real database, real web framework, real templates
```

**What gets tested:**
- HTTP routing and request handling
- Form validation logic
- Template rendering
- Database CRUD operations
- Session management
- Response redirects and status codes

**What gets mocked:**
- File system operations (`App.create()`)
- Authentication (`SessionAuthBackend.authenticate`)

## Option 2: Move to System Tests (Full Integration)

**Decision**: Move dashboard UI tests to `c_system/` and remove mocks.

**Rationale:**
- `App.create()` is core business logic, not just I/O
- File system operations are part of the application's contract
- System tests should verify the full stack including persistence
- The file system is not truly "external" - it's a primary storage mechanism

**Test Structure:**
```python
# Location: packages/hop3-server/tests/c_system/test_dashboard_app_create.py

@pytest.fixture
def test_client(tmp_path: Path, monkeypatch):
    # Configure full test environment
    monkeypatch.setattr(hop3.config, "HOP3_ROOT", tmp_path)
    monkeypatch.setattr(hop3.orm.app.c, "HOP3_ROOT", tmp_path)

    # NO MOCKS - use real App.create() implementation
    # Real database, real file system, real web framework
```

**What gets tested:**
- Everything from Option 1, plus:
- Real `App.create()` directory structure creation
- Real file system operations
- Integration of domain logic with persistence layer

**What gets mocked:**
- Only authentication (for test convenience)
- External network calls (if any)

## Detailed Design

### Option 1 Implementation

**File**: `packages/hop3-server/tests/b_integration/test_dashboard_app_create.py`

**Test Characteristics:**
- **Speed**: Fastest: no disk I/O
- **Isolation**: High - no file system side effects
- **Maintainability**: Requires maintaining mock implementation parallel to real code
- **Coverage**: Web layer + database layer only

**Mock Implementation:**
```python
def mock_app_create(self):
    """Simplified mock that just creates directories."""
    app_path = tmp_path / "apps" / self.name
    app_path.mkdir(exist_ok=True)

    for subdir in ["git", "src", "data", "logs"]:
        (app_path / subdir).mkdir(exist_ok=True)
```

**Risk**: If `App.create()` evolves (e.g., creates additional files, sets permissions, initializes git repo), the mock diverges from reality.

### Option 2 Implementation

**File**: `packages/hop3-server/tests/c_system/test_dashboard_app_create.py`

**Test Characteristics:**
- **Speed**: Slightly slower due to real I/O
- **Isolation**: Medium - creates real directories in tmp_path
- **Maintainability**: No mock to maintain, tests use real code
- **Coverage**: Full stack including file system layer

**Configuration Required:**
```python
@pytest.fixture
def test_client(tmp_path: Path, monkeypatch):
    # Must patch ALL locations where HOP3_ROOT is imported
    import hop3.config
    import hop3.orm.app

    monkeypatch.setattr(hop3.config, "HOP3_ROOT", tmp_path)
    monkeypatch.setattr(hop3.orm.app.c, "HOP3_ROOT", tmp_path)
    monkeypatch.setattr(hop3.config, "APP_ROOT", tmp_path / "apps")

    # Create required directories
    (tmp_path / "apps").mkdir(exist_ok=True)
    # ... other setup

    # NO App.create() mock - use real implementation
```

**Benefit**: Tests verify the actual behavior that users will experience.

## Examples and Interactions

### Example Test: App Creation Success

**Option 1 (Integration with Mock):**
```python
def test_app_create_success(test_client, tmp_path):
    response = test_client.post("/dashboard/apps/new", data={
        "app_name": "test-app",
        "builder": "python",
        "env_vars": "DEBUG=true"
    })

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard/apps/test-app?created=true"

    # Database verification
    with get_session() as session:
        app = session.query(App).filter_by(name="test-app").first()
        assert app is not None
        # ⚠️ File system NOT verified - mock was called instead
```

**Option 2 (System without Mock):**
```python
def test_app_create_success(test_client, tmp_path):
    response = test_client.post("/dashboard/apps/new", data={
        "app_name": "test-app",
        "builder": "python",
        "env_vars": "DEBUG=true"
    })

    assert response.status_code == 303

    # Database verification (same as before)
    with get_session() as session:
        app = session.query(App).filter_by(name="test-app").first()
        assert app is not None

    # ✅ File system verification (NEW)
    app_path = tmp_path / "apps" / "test-app"
    assert app_path.exists()
    assert (app_path / "src").exists()
    assert (app_path / "data").exists()
    assert (app_path / "logs").exists()
    assert (app_path / "git").exists()
```

### Example Test Flow Comparison

**Option 1 (Integration):**
```
User Request → Starlette → Route Handler → Form Validation
              ↓
          Database Save (SQLite, real)
              ↓
          App.create() [MOCKED - just mkdir]
              ↓
          HTTP Redirect
```

**Option 2 (System):**
```
User Request → Starlette → Route Handler → Form Validation
              ↓
          Database Save (SQLite, real)
              ↓
          App.create() [REAL - creates full directory structure]
              ↓
          HTTP Redirect
```

## Consequences

### Option 1: Integration Tests with Mocks

#### Benefits

1. **Fast Execution**: No disk I/O overhead
2. **No Side Effects**: Tests don't leave artifacts in file system
3. **Easy Setup**: Minimal fixture configuration required
4. **Focused Scope**: Tests specifically target web layer concerns
5. **Parallel Execution**: Can run multiple tests simultaneously without file conflicts

#### Drawbacks

1. **Mock Maintenance**: Must keep `mock_app_create()` in sync with real implementation
2. **Limited Coverage**: Doesn't test actual `App.create()` behavior
3. **False Confidence**: Tests might pass while real code has bugs in file operations
4. **Divergence Risk**: If `App.create()` adds logic (permissions, git init, etc.), mock won't catch it
5. **Unclear Semantics**: "Integration without file system" is ambiguous - where's the boundary?

### Option 2: System Tests without Mocks

#### Benefits

1. **Full Coverage**: Tests actual behavior users will experience
2. **No Mock Maintenance**: Tests use real code, auto-updated when implementation changes
3. **Catch Real Bugs**: Will detect issues like permission errors, path problems, etc.
4. **Clear Semantics**: "System test" clearly means "full stack with real dependencies"
5. **Better Confidence**: Tests verify the complete integration

#### Drawbacks

1. **Slightly Slower**: Real I/O adds overhead, though it remains fast
2. **More Complex Setup**: Need to patch multiple config locations
3. **Potential Brittleness**: Tests depend on more moving parts
4. **Cleanup Required**: Must ensure tmp_path cleanup works properly
5. **Less Isolation**: File system state could theoretically affect tests (mitigated by tmp_path)

## Lessons Learned

### From the Mocked Arrangement

1. **Monkeypatching is Tricky**: Patching `HOP3_ROOT` requires finding all import locations
2. **Module-Level Imports**: Config values imported at module level are hard to mock
3. **Test Classification Matters**: The choice affects where tests live and what they verify
4. **Authentication Mock is Universal**: Both options need to mock auth for convenience

### From Testing Strategy Document

The testing strategy says:
> **Integration Tests**: "Uses real database (in-memory SQLite). **No external network dependencies.**"

Note: It says "network dependencies" - not "file system dependencies". This is ambiguous.

### From Test Development Process

Mocking `App.create()` and `HOP3_ROOT` is awkward: environment-level patching and `importlib.reload()` do not work, and only monkeypatching multiple import locations plus the `App.create()` method makes the mocked tests pass. **The system fights against mocking**, which suggests that Option 2 (system tests with real implementations) is the more natural fit.

## Alternatives

### Alternative 1: Hybrid Approach

**Description**: Keep most tests in `b_integration/` with mocks, add a few smoke tests in `c_system/` without mocks.

**Example:**
- `b_integration/test_dashboard_app_create.py` - 10 tests with `App.create()` mocked
- `c_system/test_dashboard_app_create_smoke.py` - 2-3 tests using real `App.create()`

**Pros:**
- Fast feedback for common cases
- Real verification for critical paths
- Best of both worlds

**Cons:**
- Duplicated test logic
- Maintenance burden (two test suites)
- Unclear which approach to use for new tests

### Alternative 2: Refactor Domain Layer First

**Description**: Before deciding, refactor `App` class to separate concerns:
```python
class App:
    def create(self, file_system: FileSystemInterface):
        # Inject file system dependency
```

Then both options become easier:
- Integration tests: Inject mock file system
- System tests: Inject real file system

**Pros:**
- Better architecture (dependency injection)
- Easier testing at all levels
- Clearer separation of concerns

**Cons:**
- Significant refactoring required before implementing tests
- Not addressing the immediate question
- May not be worth the effort for this use case

### Alternative 3: Use E2E Tests Only

**Description**: Skip both integration and system tests, rely on E2E tests in Docker.

**Pros:**
- Maximum confidence (full production-like environment)
- No mocking or configuration complexity

**Cons:**
- Slow feedback compared to in-process tests
- Poor developer experience
- Violates testing pyramid principles

**Rejected**: E2E tests are too slow for rapid development.

## Prior Art

### Django Testing Practices

Django's test framework uses:
- **Unit tests**: Pure Python logic
- **TestCase with database**: Similar to our integration tests
- **LiveServerTestCase**: Spins up real server (like our system tests)
- **Selenium tests**: Full browser automation (like our E2E)

Django's `TestCase` uses real database but is still considered "integration" level, not "system" level.

### Rails Testing Practices

Rails uses:
- **Model tests**: Pure model logic
- **Controller tests**: Request/response with database
- **Integration tests**: Multi-controller workflows
- **System tests**: Full browser automation

Rails "controller tests" mock views but use real database - similar to Option 1.

### Fast API Testing Practices

FastAPI documentation recommends:
- **Unit tests**: Individual route handlers with mocked dependencies
- **Integration tests**: TestClient with real database
- **No official "system" layer**: Relies on E2E for full stack

FastAPI's approach aligns with **Option 1** (integration tests with some mocking).

## Unresolved Questions

1. **Where is the boundary?** What makes a dependency "external" vs "internal to the subsystem"?

2. **What about other UI features?** If we choose Option 1 for app creation, does the same apply to:
   - App deletion UI
   - App settings UI
   - Deploy/redeploy UI
   - Service management UI

3. **Configuration Management**: Should we refactor `hop3.config` to make testing easier, or accept that config patching is complex?

4. **Mock Drift**: How do we prevent mocks from diverging from real implementations? Should we have tests that verify mocks match real behavior?

5. **Performance Trade-off**: Is the slowdown from real I/O acceptable, or should we prioritize fastest possible feedback?

## Future Work

### Potential Config Refactoring

```python
# Current: Module-level constants
HOP3_ROOT = Path(os.environ.get("HOP3_ROOT", "/home/hop3"))
APP_ROOT = HOP3_ROOT / "apps"

# Future: Lazy evaluation or dependency injection
class Config:
    @property
    def HOP3_ROOT(self) -> Path:
        return Path(os.environ.get("HOP3_ROOT", "/home/hop3"))

    @property
    def APP_ROOT(self) -> Path:
        return self.HOP3_ROOT / "apps"

# Easier to mock in tests
config = Config()
```

### Test Infrastructure Improvements

1. **Shared Fixtures**: Create reusable fixtures for common test setup
2. **Factory Pattern**: Use factories for creating test data (apps, users, etc.)
3. **Custom Assertions**: Add domain-specific assertions for app state verification
4. **Test Utilities**: Helper functions for common test operations

### Documentation Updates

1. Add flowchart showing when to use each test layer
2. Provide decision tree for test placement
3. Document common patterns for UI testing
4. Add examples of all four test layers for similar features

## Related

- **[ADR 020](./020-pluggable-architecture.md)**: Pluggable Architecture - Discusses separation of concerns
- **[ADR 024](./024-backup-restore-system.md)**: Backup/Restore System - Another feature that needs testing classification
- **Testing Strategy** (`docs/src/dev/testing-strategy.md`) - Current guidelines

## References

1. Hop3 Testing Strategy: `docs/src/dev/testing-strategy.md`
2. Martin Fowler's Testing Pyramid: https://martinfowler.com/articles/practical-test-pyramid.html
3. Google Testing Blog: https://testing.googleblog.com/
4. Django Testing Documentation: https://docs.djangoproject.com/en/stable/topics/testing/
5. FastAPI Testing: https://fastapi.tiangolo.com/tutorial/testing/

## Notes

### Recommendation from ADR Author

I lean toward **Option 2 (System Tests)**: `App.create()` is core business logic rather than mere I/O, the slowdown is minimal, there is no mock to maintain, real implementations catch real bugs, and the mental model ("system tests = full stack") is simpler. **Option 1 is acceptable** only if the team prioritizes the fastest possible feedback, commits to maintaining the mock carefully, and adds system-level smoke tests separately.

### Resulting Layout (Option 2)

```
packages/hop3-server/tests/
├── a_unit/
│   └── test_app_model.py              ← Pure validation logic
├── b_integration/
│   └── test_dashboard_forms.py        ← Only form validation
├── c_system/
│   └── test_dashboard_app_create.py   ← Full stack tests
└── d_e2e/
    └── test_app_lifecycle.py          ← Complete workflows
```

Removing the `App.create()` mock simplifies the fixture rather than complicating it.
