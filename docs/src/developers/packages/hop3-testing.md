# hop3-testing Deep Dive

This document provides detailed internal documentation for the hop3-testing package. For a quick overview, see the [package overview](index.md).

## Architecture Overview

hop3-testing provides infrastructure for validating Hop3 deployments:

1. **Test Targets** - Docker containers or remote servers
2. **App Catalog** - Collection of test applications
3. **Deployment Sessions** - Automated deploy/verify/cleanup
4. **pytest Integration** - Fixtures for E2E testing

## Module Structure

```
hop3_testing/
├── __init__.py
├── main.py              # CLI entry point
├── base.py              # Base fixtures and utilities
├── common.py            # Shared utilities
├── apps/
│   ├── catalog.py       # App catalog management
│   └── deployment.py    # Deployment session handling
├── targets/
│   ├── base.py          # Abstract target interface
│   ├── docker.py        # Docker container target
│   └── remote.py        # Remote SSH target
└── util/
    ├── console.py       # Output formatting
    └── backports.py     # Python compatibility
```

## Test Targets

### Target Interface

```python
class DeploymentTarget(ABC):
    """Abstract deployment target."""

    @abstractmethod
    def setup(self) -> None:
        """Prepare target for testing."""
        ...

    @abstractmethod
    def teardown(self) -> None:
        """Clean up target after testing."""
        ...

    @abstractmethod
    def execute(self, command: str) -> CommandResult:
        """Execute command on target."""
        ...

    @abstractmethod
    def deploy_app(self, app: AppSource) -> DeploymentResult:
        """Deploy an application."""
        ...

    @abstractmethod
    def get_app_url(self, app_name: str) -> str:
        """Get URL for deployed app."""
        ...
```

### Docker Target

Runs tests in isolated Docker containers:

```python
class DockerTarget(DeploymentTarget):
    def __init__(
        self,
        image: str = "ubuntu:24.04",
        container_name: str = "hop3-test",
    ):
        self.image = image
        self.container_name = container_name
        self.client = docker.from_env()

    def setup(self) -> None:
        """Start Docker container with hop3-server."""
        self.container = self.client.containers.run(
            self.image,
            detach=True,
            name=self.container_name,
            privileged=True,  # For systemd
            ports={"8000/tcp": None, "80/tcp": None},
        )

        # Install hop3-server
        self.execute("curl ... | python3 -")

        # Wait for server to be ready
        self.wait_for_ready()

    def teardown(self) -> None:
        """Stop and remove container."""
        self.container.stop()
        self.container.remove()

    def execute(self, command: str) -> CommandResult:
        """Execute command in container."""
        exit_code, output = self.container.exec_run(command)
        return CommandResult(exit_code, output.decode())
```

### Remote Target

Runs tests against a remote Hop3 server:

```python
class RemoteTarget(DeploymentTarget):
    def __init__(
        self,
        host: str,
        ssh_key: Path | None = None,
        user: str = "hop3",
    ):
        self.host = host
        self.ssh_key = ssh_key
        self.user = user

    def setup(self) -> None:
        """Verify remote server is ready."""
        result = self.execute("hop3-server --version")
        if result.exit_code != 0:
            raise TargetNotReadyError(f"Server not ready: {result.output}")

    def teardown(self) -> None:
        """Clean up test apps."""
        # Remove all test apps
        result = self.execute("hop3 apps --json")
        apps = json.loads(result.output)
        for app in apps:
            if app["name"].startswith("test-"):
                self.execute(f"hop3 app destroy {app['name']} --confirm")

    def execute(self, command: str) -> CommandResult:
        """Execute command via SSH."""
        ssh_cmd = ["ssh"]
        if self.ssh_key:
            ssh_cmd.extend(["-i", str(self.ssh_key)])
        ssh_cmd.extend([f"{self.user}@{self.host}", command])

        result = subprocess.run(ssh_cmd, capture_output=True)
        return CommandResult(result.returncode, result.stdout.decode())
```

## App Catalog

Collection of test applications:

### Catalog Structure

```
apps/test-apps/
├── 010-flask-pip-wsgi/
│   ├── app.py
│   ├── requirements.txt
│   ├── Procfile
│   └── test.yaml          # Test metadata
├── 020-nodejs-express/
│   ├── app.js
│   ├── package.json
│   └── test.yaml
└── ...
```

### Test Metadata

```yaml
# test.yaml
name: flask-pip-wsgi
category: python-simple
runtime: python
description: Simple Flask app with pip requirements

tests:
  - name: http_check
    type: http
    path: /
    expect:
      status: 200
      contains: "Hello"

  - name: health_check
    type: http
    path: /health
    expect:
      status: 200

timeout: 120  # seconds
```

### Catalog API

```python
class AppSourceCatalog:
    """Manage test application catalog."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self._apps: dict[str, AppSource] = {}
        self._load_catalog()

    def _load_catalog(self) -> None:
        """Load all apps from catalog directory."""
        for app_dir in self.base_path.iterdir():
            if app_dir.is_dir() and (app_dir / "test.yaml").exists():
                app = AppSource.from_directory(app_dir)
                self._apps[app.name] = app

    def get(self, name: str) -> AppSource:
        """Get app by name."""
        return self._apps[name]

    def filter_by_category(self, category: str) -> list[AppSource]:
        """Get apps by category."""
        return [a for a in self._apps.values() if a.category == category]

    def all(self) -> list[AppSource]:
        """Get all apps."""
        return list(self._apps.values())
```

## Deployment Sessions

Manages the deploy/verify/cleanup lifecycle:

```python
class DeploymentSession:
    """Context manager for deployment testing."""

    def __init__(self, target: DeploymentTarget, app: AppSource):
        self.target = target
        self.app = app
        self.deployed = False

    def __enter__(self) -> "DeploymentSession":
        self.deploy()
        return self

    def __exit__(self, *args) -> None:
        self.cleanup()

    def deploy(self) -> None:
        """Deploy the application."""
        result = self.target.deploy_app(self.app)
        if not result.success:
            raise DeploymentError(result.error)
        self.deployed = True

    def verify_running(self) -> bool:
        """Check if app is running."""
        result = self.target.execute(f"hop3 app show {self.app.name} --json")
        info = json.loads(result.output)
        return info["state"] == "running"

    def verify_http_response(self) -> bool:
        """Verify HTTP endpoint responds."""
        url = self.target.get_app_url(self.app.name)
        response = requests.get(url, timeout=10)
        return response.status_code == 200

    def run_tests(self) -> TestResults:
        """Run all tests defined in test.yaml."""
        results = TestResults()
        for test in self.app.tests:
            result = self._run_test(test)
            results.add(result)
        return results

    def cleanup(self) -> None:
        """Remove deployed app."""
        if self.deployed:
            self.target.execute(f"hop3 app destroy {self.app.name} --confirm")
```

## pytest Integration

### Fixtures

```python
# conftest.py
import pytest
from hop3_testing import DockerTarget, AppSourceCatalog

@pytest.fixture(scope="session")
def deployment_target():
    """Provide deployment target for tests."""
    target = DockerTarget()
    target.setup()
    yield target
    target.teardown()

@pytest.fixture(scope="session")
def app_catalog():
    """Provide app catalog."""
    return AppSourceCatalog(Path("apps/test-apps"))

@pytest.fixture
def deployment_session(deployment_target, app_catalog, request):
    """Provide deployment session for specific app."""
    app_name = getattr(request, "param", "010-flask-pip-wsgi")
    app = app_catalog.get(app_name)
    with DeploymentSession(deployment_target, app) as session:
        yield session
```

### Example Test

```python
@pytest.mark.parametrize("deployment_session", [
    "010-flask-pip-wsgi",
    "020-nodejs-express",
], indirect=True)
def test_app_deployment(deployment_session):
    """Test application deployment."""
    assert deployment_session.verify_running()
    assert deployment_session.verify_http_response()

    results = deployment_session.run_tests()
    assert results.all_passed()
```

## CLI Interface

```bash
# Run all tests
hop3-test --target docker

# Run specific app
hop3-test --target docker 010-flask-pip-wsgi

# Run by category
hop3-test --target docker --category python-simple

# Run against remote server
hop3-test --target remote --host hop3.example.com

# List available apps
hop3-test --list-apps

# Verbose output
hop3-test --target docker -v
```

### CLI Implementation

```python
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["docker", "remote"], required=True)
    parser.add_argument("--host", help="Remote host (for remote target)")
    parser.add_argument("--category", help="Filter by category")
    parser.add_argument("apps", nargs="*", help="Apps to test")
    args = parser.parse_args()

    # Create target
    if args.target == "docker":
        target = DockerTarget()
    else:
        target = RemoteTarget(args.host)

    # Load catalog
    catalog = AppSourceCatalog(CATALOG_PATH)

    # Filter apps
    if args.apps:
        apps = [catalog.get(name) for name in args.apps]
    elif args.category:
        apps = catalog.filter_by_category(args.category)
    else:
        apps = catalog.all()

    # Run tests
    runner = TestRunner(target, apps)
    results = runner.run()

    # Report
    reporter = ResultReporter(results)
    reporter.print_summary()

    sys.exit(0 if results.all_passed() else 1)
```

## App Categories

| Category | Description | Examples |
|----------|-------------|----------|
| `python-simple` | Basic Python apps | Flask, FastAPI |
| `python-complex` | Multi-process Python | Django + Celery |
| `nodejs` | Node.js applications | Express, Fastify |
| `ruby` | Ruby applications | Sinatra, Rails |
| `go` | Go applications | Fiber, Gin |
| `rust` | Rust applications | Actix-web, Axum |
| `static` | Static sites | HTML, Hugo, Jekyll |
| `docker` | Docker-based apps | Dockerfile builds |

## Test Types

### HTTP Tests

```yaml
tests:
  - name: homepage
    type: http
    method: GET
    path: /
    expect:
      status: 200
      contains: "Welcome"
      headers:
        content-type: "text/html"
```

### Command Tests

```yaml
tests:
  - name: health_check
    type: command
    command: "hop3 app show {app_name} --json"
    expect:
      exit_code: 0
      json:
        state: "running"
```

### Log Tests

```yaml
tests:
  - name: no_errors
    type: logs
    expect:
      not_contains: ["ERROR", "CRITICAL"]
```

## Debugging

### Verbose Mode

```bash
hop3-test --target docker -vvv
```

### Keep Target Running

```bash
hop3-test --target docker --keep-target
# After tests, container remains running for inspection
docker exec -it hop3-test bash
```

### Single App Test

```bash
hop3-test --target docker 010-flask-pip-wsgi -v --keep-target
```
