# Testing Strategy

This document outlines Hop3's comprehensive testing strategy, covering unit tests, integration tests, system integration tests, and full end-to-end tests.

## Overview

Hop3 uses a four-layer testing pyramid to ensure code quality, catch regressions early, and validate the complete system behavior.

```
                    ▲
                   ╱│╲
                  ╱ │ ╲
                 ╱  │  ╲
                ╱   │   ╲    Layer 4: Full E2E Tests (d_e2e/)
               ╱────┼────╲   Real deployments, nginx, systemd
              ╱     │     ╲  ~20 tests, 10-20 min
             ╱──────┼──────╲
            ╱       │       ╲
           ╱────────┼────────╲  Layer 3: System Integration (c_system/)
          ╱         │         ╲ CLI ↔ Server communication
         ╱──────────┼──────────╲ ~30 tests, 2-5 min
        ╱           │           ╲
       ╱────────────┼────────────╲  Layer 2: Integration Tests (b_integration/)
      ╱             │             ╲ Multiple components, no external deps
     ╱──────────────┼──────────────╲ ~50 tests, 30-60 sec
    ╱               │               ╲
   ╱────────────────┼────────────────╲  Layer 1: Unit Tests (a_unit/)
  ╱_________________│_________________╲ Individual components
 ╱_____________________________________╲ ~200+ tests, 5-15 sec
```

## Layer 1: Unit Tests (`tests/a_unit/`)

### Purpose
Test individual functions, classes, and modules in complete isolation.

### Characteristics
- ✅ Fast execution (< 1ms per test)
- ✅ No external dependencies
- ✅ Use mocks and fakes liberally
- ✅ Test edge cases and error conditions
- ❌ No database connections
- ❌ No file I/O (use temp directories or mocks)
- ❌ No network calls

### Structure
```
tests/a_unit/
├── commands/          # Command classes
├── orm/              # Database models (using in-memory SQLite)
├── server/           # Server components
├── plugins/          # Plugin implementations
└── test_*.py         # Miscellaneous unit tests
```

### Example
```python
# tests/a_unit/test_archives.py

def test_is_safe_filename_rejects_path_traversal():
    """Test that path traversal attempts are rejected."""
    assert not is_safe_filename("../etc/passwd")
    assert not is_safe_filename("foo/../../etc/passwd")

def test_is_safe_filename_accepts_normal_paths():
    """Test that normal filenames are accepted."""
    assert is_safe_filename("foo.txt")
    assert is_safe_filename("dir/foo.txt")
```

### Current Status
✅ **133 tests passing**

### Guidelines
- Each test should complete in < 10ms
- Aim for > 80% code coverage
- Test both success and failure paths
- Use descriptive test names: `test_<action>_<expected_result>`

---

## Layer 2: Integration Tests (`tests/b_integration/`)

### Purpose
Test how multiple components work together within a subsystem, without requiring external infrastructure.

### Characteristics
- ✅ Use Starlette TestClient (no real server process)
- ✅ Use in-memory or temporary databases
- ✅ Use temporary file systems
- ✅ Test interactions between 2-5 components
- ❌ No SSH connections
- ❌ No real Linux system operations
- ❌ No deployed applications

### Structure
```
tests/b_integration/
├── test_rpc_auth.py         # RPC + Auth middleware
├── test_rpc_security.py     # RPC + Security
├── test_deployment_flow.py  # Deployer + Builder (temp dirs)
└── test_service_lifecycle.py # Service framework + PostgreSQL
```

### Example
```python
# tests/b_integration/test_rpc_security.py

def test_authenticated_command_requires_token(client: TestClient):
    """Test that authenticated commands reject requests without tokens."""
    response = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cli_args": ["apps"], "extra_args": {}},
            "id": 1,
        }
    )

    assert response.status_code == 401
    data = response.json()
    assert "Authentication required" in data["error"]["message"]
```

### Current Status
✅ **20 security tests passing**

### Guidelines
- Each test should complete in < 1 second
- Use TestClient instead of real HTTP requests
- Use temporary directories for file operations
- Mock external services (nginx, systemd)
- Test failure scenarios and error handling

---

## Layer 3: System Integration Tests (`tests/c_system/`)

### Purpose
Test the complete client-server interaction, including CLI, RPC protocol, and authentication, but without deploying actual applications.

### Characteristics
- ✅ Real hop3-server process (localhost or remote)
- ✅ Real hop3-cli binary
- ✅ Real RPC communication over HTTP
- ✅ Real authentication flow (JWT tokens)
- ✅ Real database operations
- ❌ No actual app deployments
- ❌ No nginx/uwsgi configuration
- ❌ No systemd services

### Structure
```
tests/c_system/
├── conftest.py              # Server fixtures
├── test_connection.py       # Basic connectivity
├── test_auth_flow.py        # Registration, login, token refresh
├── test_app_management.py   # Deploy, start, stop, destroy (mocked)
└── test_service_commands.py # Service CRUD operations
```

### Example
```python
# tests/c_system/test_auth_flow.py

def test_full_authentication_flow(hop3_server):
    """Test complete user registration and login."""
    username = f"testuser-{int(time.time())}"

    # Register user
    result = subprocess.run(
        ["hop3", "auth:register", username, f"{username}@example.com", "password123"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0

    # Login
    result = subprocess.run(
        ["hop3", "auth:login", username, "password123"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "Your API token:" in result.stdout

    # Extract token
    token = extract_token(result.stdout)
    assert token

    # Use token to call authenticated command
    os.environ["HOP3_API_TOKEN"] = token
    result = subprocess.run(
        ["hop3", "apps"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
```

### Current Status
✅ **Infrastructure created**
⚠️  **Requires server setup** (python3-venv installation)

### Server Setup
System tests require a running hop3-server. Two options:

**Option A: Local Server (Development)**
```bash
# Terminal 1: Start server
hop-server serve

# Terminal 2: Run tests
export HOP3_API_URL=http://localhost:8000
pytest tests/c_system/
```

**Option B: Remote Server (CI)**
```bash
export HOP3_DEV_HOST=hop3@test-server.example.com
pytest tests/c_system/
```

### Guidelines
- Tests should use subprocess to call `hop3` CLI
- Clean up created resources (users, apps) in fixtures
- Use unique names (timestamps) to avoid conflicts
- Each test should complete in < 5 seconds
- Test both success and error responses

---

## Layer 4: Full End-to-End Tests (`tests/d_e2e/`)

### Purpose
Test the complete system including actual application deployments, web server configuration, and HTTP responses.

### Characteristics
- ✅ Full Linux environment
- ✅ Real application deployments
- ✅ Real nginx configuration
- ✅ Real uwsgi/systemd processes
- ✅ Real HTTP responses from deployed apps
- ✅ Real SSL/TLS (Let's Encrypt in production mode)

### Structure
```
tests/d_e2e/
├── docker/
│   ├── Dockerfile.hop3-server    # Container image
│   ├── entrypoint.sh             # Systemd initialization
│   └── hop3-server.conf          # Server config
├── conftest.py                   # Container fixtures
├── test_apps/                    # Test application templates
│   ├── python-flask/
│   ├── nodejs-express/
│   └── ruby-sinatra/
├── test_python_deployment.py    # Python app tests
├── test_nodejs_deployment.py    # Node.js app tests
└── test_lifecycle.py             # Start, stop, restart, destroy
```

### Test Applications
E2E tests use sample applications from `apps/test-apps/`:

- **000-static**: Static HTML site
- **010-flask-pip-wsgi**: Python Flask with pip/wsgi
- **020-nodejs-express**: Node.js Express app
- **030-golang-gin**: Go web application
- **040-sinatra**: Ruby Sinatra app
- **100-flask-gunicorn-pip**: Python Flask with Gunicorn
- **110-flask-gunicorn-poetry**: Python Flask with Poetry

Each test app includes:
- Application source code
- `Procfile` or `hop3.toml`
- `check.py` script for validation (optional)

### Example
```python
# tests/d_e2e/test_python_deployment.py

def test_deploy_flask_app(hop3_container, tmp_path):
    """Test deploying a Flask application."""
    app_name = f"test-flask-{int(time.time())}"

    # Create test app
    app_dir = tmp_path / "flask-app"
    app_dir.mkdir()
    (app_dir / "app.py").write_text('''
from flask import Flask
app = Flask(__name__)

@app.route("/")
def index():
    return "Hello from Flask!"
''')
    (app_dir / "requirements.txt").write_text("flask\n")
    (app_dir / "Procfile").write_text("web: python app.py\n")

    # Deploy via git push
    with chdir(app_dir):
        run("git init")
        run("git add .")
        run("git commit -m 'Initial commit'")
        run(f"git remote add hop3 {hop3_container['ssh_config']}")
        run("git push hop3 main")

    # Wait for deployment
    time.sleep(10)

    # Test HTTP response
    response = httpx.get(f"{hop3_container['http_base']}/{app_name}/")
    assert response.status_code == 200
    assert "Hello from Flask!" in response.text

    # Cleanup
    run(f"hop3 destroy {app_name}")
```

### Infrastructure: Docker-Based

E2E tests run in isolated Docker containers with systemd support:

```dockerfile
# tests/d_e2e/docker/Dockerfile.hop3-server

FROM ubuntu:22.04

# Install systemd
RUN apt-get update && \
    apt-get install -y systemd systemd-sysv && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Hop3 dependencies
COPY installer/requirements.txt /tmp/
RUN apt-get update && \
    apt-get install -y $(cat /tmp/requirements.txt) && \
    apt-get clean

# Create hop3 user
RUN useradd -m -s /bin/bash -G www-data hop3

# Copy and install hop3
COPY dist/hop3_server-*.tar.gz /tmp/
RUN su - hop3 -c "python3 -m venv ~/venv && \
    ~/venv/bin/pip install /tmp/hop3_server-*.tar.gz"

# Setup hop3
RUN su - hop3 -c "~/venv/bin/hop-server setup"

# Copy systemd service
COPY tests/d_e2e/docker/hop3-server.service /etc/systemd/system/
RUN systemctl enable hop3-server

EXPOSE 22 80 443

ENTRYPOINT ["/lib/systemd/systemd"]
```

### Container Lifecycle
```python
@pytest.fixture(scope="class")
def hop3_container():
    """Provide a fresh hop3 container for each test class."""
    client = docker.from_env()

    # Start container
    container = client.containers.run(
        "hop3-e2e:latest",
        detach=True,
        privileged=True,  # Required for systemd
        publish_all_ports=True,
    )

    # Wait for services
    wait_for_ssh(container)
    wait_for_http(container)

    yield container

    # Cleanup
    container.stop(timeout=5)
    container.remove()
```

### Current Status
⏳ **Not yet implemented**

### Roadmap
1. **Phase 1**: Create Dockerfile and basic fixtures (2-3 days)
2. **Phase 2**: Port 5 test apps from hop3-testing (2-3 days)
3. **Phase 3**: GitHub Actions integration (1-2 days)

### Guidelines
- Each test should be independent and idempotent
- Use unique app names (timestamps or UUIDs)
- Clean up deployed apps in teardown
- Test should complete in < 60 seconds
- Log container output on failure
- Use container snapshots for faster restarts

---

## Running Tests

### Run All Tests
```bash
# All tests (unit + integration + system + e2e)
pytest

# With coverage
pytest --cov=hop3 --cov-report=html
```

### Run Specific Layers
```bash
# Unit tests only (fast)
pytest tests/a_unit/

# Integration tests only
pytest tests/b_integration/

# System integration tests (requires server)
pytest tests/c_system/

# Full E2E tests (requires Docker)
pytest tests/d_e2e/
```

### Run Specific Test Files
```bash
# Single file
pytest tests/a_unit/test_archives.py

# Single test
pytest tests/a_unit/test_archives.py::test_is_safe_filename_accepts_normal_paths

# Tests matching pattern
pytest -k "auth"
```

### Debug Options
```bash
# Verbose output
pytest -v

# Show print statements
pytest -s

# Stop on first failure
pytest -x

# Enter debugger on failure
pytest --pdb
```

---

## Continuous Integration

### GitHub Actions Workflow

```yaml
name: Tests

on: [push, pull_request]

jobs:
  unit-and-integration:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install uv
          uv sync

      - name: Run unit tests
        run: uv run pytest tests/a_unit/ -v

      - name: Run integration tests
        run: uv run pytest tests/b_integration/ -v

  system-integration:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Start hop3-server
        run: |
          uv sync
          uv run hop-server serve &
          sleep 5

      - name: Run system tests
        run: |
          export HOP3_API_URL=http://localhost:8000
          uv run pytest tests/c_system/ -v

  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Build hop3 packages
        run: |
          uv sync
          uv build

      - name: Build E2E Docker image
        run: |
          docker build -f tests/d_e2e/docker/Dockerfile.hop3-server \
            -t hop3-e2e:latest .

      - name: Run E2E tests
        run: |
          uv run pytest tests/d_e2e/ -v --log-cli-level=INFO
```

---

## Test Coverage Goals

| Layer | Current | Target | Priority |
|-------|---------|--------|----------|
| Unit Tests | 133 tests | 250+ tests | High |
| Integration Tests | 20 tests | 60+ tests | High |
| System Integration | 6 tests | 40+ tests | Medium |
| Full E2E | 0 tests | 25+ tests | Medium |
| **Total** | **159 tests** | **375+ tests** | - |

### Coverage Metrics
- **Overall code coverage**: Target > 75%
- **Core modules**: Target > 85%
  - `hop3/orm/` (models)
  - `hop3/commands/` (CLI commands)
  - `hop3/server/` (web server)
  - `hop3/plugins/build/` (builders)

---

## Migration from hop3-testing

The existing `hop3-testing` package will be gradually replaced:

### Current (hop3-testing)
- Standalone CLI tool (`hop-test`)
- Uses pre-configured test server
- Custom test runner
- 19 test applications

### Future (pytest-based)
- Integrated with pytest
- Docker-based isolation
- Same test applications
- Better CI/CD integration

### Migration Plan
1. **Keep hop3-testing** for manual testing and debugging
2. **Create pytest equivalents** in `tests/d_e2e/`
3. **Reuse test apps** from `apps/test-apps/`
4. **Deprecate hop3-testing** once pytest suite is complete

---

## Best Practices

### Test Naming
```python
# Good
def test_deploy_creates_app_directory()
def test_invalid_token_returns_401()
def test_missing_procfile_raises_error()

# Bad
def test_deploy()
def test_auth()
def test_error()
```

### Test Structure (Arrange-Act-Assert)
```python
def test_create_user_with_valid_data():
    # Arrange
    username = "testuser"
    email = "test@example.com"
    password = "secure123"

    # Act
    user = User.create(username, email, password)

    # Assert
    assert user.username == username
    assert user.email == email
    assert user.verify_password(password)
```

### Fixtures Over Setup/Teardown
```python
# Good
@pytest.fixture
def temp_app_dir(tmp_path):
    app_dir = tmp_path / "myapp"
    app_dir.mkdir()
    yield app_dir
    # Cleanup automatic with tmp_path

def test_something(temp_app_dir):
    # Use fixture
    pass

# Avoid
def setup_method():
    self.app_dir = Path("/tmp/myapp")
    self.app_dir.mkdir()

def teardown_method():
    shutil.rmtree(self.app_dir)
```

### Parametrized Tests
```python
@pytest.mark.parametrize("filename,expected", [
    ("foo.txt", True),
    ("../etc/passwd", False),
    ("dir/foo.txt", True),
    ("foo/../../etc/passwd", False),
])
def test_is_safe_filename(filename, expected):
    assert is_safe_filename(filename) == expected
```

---

## Troubleshooting

### System Tests Fail to Connect to Server
```bash
# Check if server is running
curl http://localhost:8000/health

# Check server logs
journalctl -u hop3-server -f

# Verify SSH tunnel
hop3 apps  # Should not hang
```

### E2E Tests Fail to Start Container
```bash
# Check Docker daemon
docker info

# Check image exists
docker images | grep hop3-e2e

# Rebuild image
docker build -f tests/d_e2e/docker/Dockerfile.hop3-server \
  -t hop3-e2e:latest .
```

### Tests Pass Locally but Fail in CI
- Check environment variables
- Verify GitHub Actions has enough resources
- Check for timing issues (add appropriate sleeps)
- Review CI logs for error messages

---

## References

- [pytest Documentation](https://docs.pytest.org/)
- [Docker systemd](https://github.com/docker-systemd/docker-systemd)
- [Testing Best Practices](https://docs.python-guide.org/writing/tests/)
- [Test-Driven Development](https://en.wikipedia.org/wiki/Test-driven_development)
