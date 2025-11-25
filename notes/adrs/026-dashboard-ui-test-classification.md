# ADR 026: Dashboard UI Test Classification - Integration vs System Tests

Status: **Accepted** (2025-11-20, updated 2025-11-25)

## Introduction

This ADR addresses the question of how to properly classify and implement tests for the Hop3 dashboard web UI, specifically focusing on where the boundary lies between integration tests and system tests when testing web application features.

## Summary

Dashboard UI tests that involve file system operations have been moved to system tests (`c_system/`) with real `App.create()` implementation, rather than remaining as integration tests with mocked file operations.

## Context and Goals

### Context

The dashboard app creation feature (`/dashboard/apps/new`) has 10 tests that verify:
- Form rendering and validation (5 tests)
- App creation with database persistence (5 tests)

Current implementation (`packages/hop3-server/tests/b_integration/test_dashboard_app_create.py`):
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

**What the tests currently verify:**
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

**DECISION: Option 2 - Move to System Tests**

Dashboard UI tests for the app creation feature have been moved from `b_integration/` to `c_system/` and now use the real `App.create()` implementation without mocks.

**Rationale:**
1. `App.create()` is core business logic that creates the application's directory structure
2. The performance overhead is negligible (~0.6s vs estimated ~1.3-1.5s if we had more file operations)
3. Removes mock maintenance burden - tests use real code
4. Better bug detection - already caught a test assumption error (log vs logs directory name)
5. Clearer semantics - "system test" clearly means "full stack with real dependencies"

**Implementation:**
- Tests moved to: `packages/hop3-server/tests/c_system/test_dashboard_app_create.py`
- `App.create()` mock removed
- Added file system verification assertions
- All 10 tests passing with real implementation

**What's tested:**
- Real HTTP request/response cycle (Starlette)
- Real route handlers and form validation
- Real database operations (SQLAlchemy + SQLite)
- Real template rendering (Jinja2)
- **Real file system operations** (App.create() directory creation)
- Only authentication is mocked for test convenience

## Option 1: Keep as Integration Tests (Current Approach)

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

### Option 1 Implementation (Current)

**File**: `packages/hop3-server/tests/b_integration/test_dashboard_app_create.py`

**Test Characteristics:**
- **Speed**: ~0.8 seconds for 10 tests
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

### Option 2 Implementation (Proposed)

**File**: `packages/hop3-server/tests/c_system/test_dashboard_app_create.py`

**Test Characteristics:**
- **Speed**: ~1-2 seconds for 10 tests (slightly slower due to real I/O)
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

**Current (Integration with Mock):**
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

**Proposed (System without Mock):**
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

1. **Fast Execution**: No disk I/O overhead (~0.8s for 10 tests)
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

1. **Slightly Slower**: Real I/O adds ~0.5-1s overhead (still fast: ~1-2s total)
2. **More Complex Setup**: Need to patch multiple config locations
3. **Potential Brittleness**: Tests depend on more moving parts
4. **Cleanup Required**: Must ensure tmp_path cleanup works properly
5. **Less Isolation**: File system state could theoretically affect tests (mitigated by tmp_path)

## Lessons Learned

### From Current Implementation

1. **Monkeypatching is Tricky**: Patching `HOP3_ROOT` required finding all import locations
2. **Module-Level Imports**: Config values imported at module level are hard to mock
3. **Test Classification Matters**: The choice affects where tests live and what they verify
4. **Authentication Mock is Universal**: Both options need to mock auth for convenience

### From Testing Strategy Document

The testing strategy says:
> **Integration Tests**: "Uses real database (in-memory SQLite). **No external network dependencies.**"

Note: It says "network dependencies" - not "file system dependencies". This is ambiguous.

### From Test Development Process

1. First attempt: Tried to mock `HOP3_ROOT` at environment level → Failed
2. Second attempt: Used `importlib.reload()` → Failed
3. Third attempt: Monkeypatched multiple locations → Partially worked
4. Fourth attempt: Added `App.create()` mock → All tests passed

This progression suggests that **the system fought against mocking**, which might indicate that Option 2 (system tests) is more natural.

## Action Items

### If Option 1 is Chosen (Keep as Integration Tests)

1. Document the mock in comments explaining what it simulates
2. Add a system test that verifies real `App.create()` behavior separately
3. Update testing strategy to clarify "file system is external dependency"
4. Consider adding property-based tests for `App.create()` in `a_unit/`

### If Option 2 is Chosen (Move to System Tests)

1. Move `test_dashboard_app_create.py` from `b_integration/` to `c_system/`
2. Remove `App.create()` mock from test fixture
3. Fix all config patching to work with real implementation
4. Add assertions verifying file system state after app creation
5. Update test to verify actual directory permissions if relevant
6. Update testing strategy with examples of system-level UI tests

### Common Actions (Regardless of Decision)

1. Document the decision in this ADR
2. Update testing guidelines with clear criteria for future dashboard tests
3. Add examples to testing strategy documentation
4. Consider refactoring config module to make testing easier (future work)

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
- Very slow feedback (10-20 minutes vs 1 second)
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

5. **Performance Trade-off**: Is the ~0.5-1s slowdown for real I/O acceptable, or should we prioritize fastest possible feedback?

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

- **ADR 020**: Pluggable Architecture - Discusses separation of concerns
- **ADR 024**: Backup/Restore System - Another feature that needs testing classification
- **Testing Strategy** (`docs/src/dev/testing-strategy.md`) - Current guidelines

## References

1. Hop3 Testing Strategy: `docs/src/dev/testing-strategy.md`
2. Martin Fowler's Testing Pyramid: https://martinfowler.com/articles/practical-test-pyramid.html
3. Google Testing Blog: https://testing.googleblog.com/
4. Django Testing Documentation: https://docs.djangoproject.com/en/stable/topics/testing/
5. FastAPI Testing: https://fastapi.tiangolo.com/tutorial/testing/

## Notes

### Decision Factors to Consider

When choosing between the two options, consider:

1. **Team Velocity**: How important is fast feedback vs comprehensive testing?
2. **Bug History**: Has `App.create()` had bugs that mocks would have missed?
3. **Change Frequency**: How often does the file system logic change?
4. **Test Maintainability**: Which approach is easier for new contributors?
5. **CI/CD Pipeline**: What's the acceptable test suite runtime?

### Recommendation from ADR Author

**Personal Opinion** (to be validated by team):

I lean toward **Option 2 (System Tests)** for these reasons:

1. **`App.create()` is core business logic**, not just I/O
2. **The slowdown is minimal** (0.5-1s is acceptable)
3. **No mock to maintain** reduces long-term burden
4. **Better bug detection** - will catch real issues
5. **Simpler mental model** - "system tests = full stack"

However, **Option 1 is acceptable** if:
- The team prioritizes fastest possible feedback
- We commit to maintaining the mock carefully
- We add system-level smoke tests separately

## Appendix

### Current Test Results

**With Mocks** (Option 1):
```bash
$ pytest packages/hop3-server/tests/b_integration/test_dashboard_app_create.py -v
======================== 10 passed, 1 warning in 0.79s =========================
```

**Test Breakdown:**
- 5 validation tests (no mocks needed): 0.3s
- 5 app creation tests (mocks used): 0.5s

**Estimated with Real I/O** (Option 2):
- 5 validation tests: 0.3s (same)
- 5 app creation tests: 1.0-1.2s (with real file operations)
- **Total estimated: 1.3-1.5s**

### Actual Implementation Results

**Final Test Results** (Option 2 - System Tests):
```bash
$ pytest packages/hop3-server/tests/c_system/test_dashboard_app_create.py -v
======================== 10 passed, 1 warning in 0.62s =========================
```

**Performance:** 0.62s for 10 tests (even faster than the estimated 1.3-1.5s!)

**Bug Found During Migration:**
The test initially assumed the log directory would be named `logs` (plural), but the real implementation creates `log` (singular) as defined in `App.log_path` property. This demonstrates the value of using real implementations - the mock would have hidden this discrepancy indefinitely.

**Fixture Complexity:**
- Before (with mock): ~28 lines including 15-line App.create() mock
- After (without mock): ~25 lines, simpler and more maintainable

### File Structure Comparison

**Old Structure** (Option 1 - Not Chosen):
```
packages/hop3-server/tests/
├── a_unit/
│   └── (future: test_app_model.py with pure logic tests)
├── b_integration/
│   └── test_dashboard_app_create.py    ← Currently here (10 tests)
├── c_system/
│   └── (empty for dashboard tests)
└── d_e2e/
    └── (future: full workflow tests)
```

**Implemented Structure** (Option 2 - Chosen):
```
packages/hop3-server/tests/
├── a_unit/
│   └── test_app_model.py              ← Pure validation logic
├── b_integration/
│   └── test_dashboard_forms.py        ← Only form validation (5 tests)
├── c_system/
│   └── test_dashboard_app_create.py   ← Full stack tests (10 tests)
└── d_e2e/
    └── test_app_lifecycle.py          ← Complete workflows
```

### Code Complexity Comparison

**Option 1 Fixture** (current):
```python
@pytest.fixture
def test_client(tmp_path: Path, monkeypatch):
    # 3 lines: patch config
    # 15 lines: mock App.create()
    # 5 lines: mock auth
    # 5 lines: setup app
    # Total: ~28 lines
```

**Option 2 Fixture** (proposed):
```python
@pytest.fixture
def test_client(tmp_path: Path, monkeypatch):
    # 5 lines: patch all config locations
    # 8 lines: create directory structure
    # 5 lines: mock auth only
    # 5 lines: setup app
    # Total: ~23 lines (simpler!)
```

Removing the `App.create()` mock actually **simplifies** the fixture.
