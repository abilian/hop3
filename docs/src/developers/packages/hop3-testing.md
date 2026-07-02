# hop3-testing Deep Dive

This document provides detailed internal documentation for the hop3-testing package. For a quick overview, see the [package overview](index.md).

## Architecture Overview

hop3-testing provides infrastructure for validating Hop3 deployments:

1. **Test Targets** - Docker containers or remote SSH servers
2. **Catalog** - Discovery of tests defined in `hop3.toml` (or standalone `test.toml`)
3. **Deployment Sessions** - Automated deploy/verify/cleanup
4. **Runners** - Deployment, demo, and tutorial execution strategies
5. **pytest Integration** - the `c_e2e` layer that drives real deploys

The `hop3-test` CLI exposes four subcommands: `run`, `list`, `cloud`, and `why`.

## Module Structure

```
hop3_testing/
├── __init__.py
├── cli/                  # CLI commands and helpers
│   ├── __init__.py       # `cli` group + `main` entry point
│   ├── commands/         # Click command implementations
│   │   ├── test.py       # `run`
│   │   ├── catalog.py    # `list`
│   │   ├── cloud.py      # `cloud`
│   │   └── why.py        # `why`
│   ├── runners.py        # Test execution orchestration
│   └── helpers.py        # Target creation helpers
├── catalog/
│   ├── scanner.py        # Catalog - scans for hop3.toml + standalone test.toml
│   ├── loader.py         # Reads [test] from hop3.toml; falls back to test.toml
│   └── models.py         # TestDefinition, Tier, Priority, TargetType
├── apps/
│   ├── catalog.py        # AppSource dataclass
│   └── deployment.py     # DeploymentSession - deploy/verify/cleanup
├── targets/
│   ├── base.py           # DeploymentTarget ABC, TargetInfo, CommandResult
│   ├── config.py         # DeploymentConfig, DockerConfig, RemoteConfig
│   ├── docker.py         # DockerTarget
│   └── remote.py         # RemoteTarget
├── runners/              # Deployment, demo, tutorial runners
├── results/              # SQLite result storage and reporters
├── selector/             # Test selection by mode
├── system_tests/         # Cloud (Hetzner) E2E orchestration
└── util/
    └── console.py        # Output formatting
```

## Test Targets

### Target Interface

`DeploymentTarget` (`targets/base.py`) is the abstract base every target implements. Only `start` and `stop` are abstract; the higher-level operations (`exec_run`, `deploy_app`, `destroy_app`, `get_app_url`, `run_command`, `http_request`, `wait_for_app`, context-manager support) are concrete methods built on those two primitives:

```python
class DeploymentTarget(ABC):
    """Abstract base class for deployment targets."""

    @abstractmethod
    def start(self) -> TargetInfo:
        """Start the target and return its connection details."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop and clean up the target."""
        ...

    def exec_run(self, cmd: str | list[str]) -> tuple[int, str, str]:
        """Run a command on the target, returning (exit_code, stdout, stderr)."""
        ...

    def deploy_app(
        self, app_path: Path, app_name: str, ...
    ) -> DeployResult:
        """Create a tarball and deploy the application via hop3."""
        ...

    def destroy_app(self, app_name: str) -> None:
        """Tear down a deployed application."""
        ...

    def get_app_url(self, app_name: str) -> str:
        """Return the externally reachable URL for a deployed app."""
        ...
```

### Docker Target

`DockerTarget` (`targets/docker.py`) runs tests in an isolated Docker container, configured through a `DockerConfig` dataclass:

```python
from hop3_testing.targets import DockerTarget, DockerConfig, DeploymentConfig

# App testing against a pre-built image (fast)
target = DockerTarget(DockerConfig(image="hop3-ready:latest"))

# System testing: deploy Hop3 from local code into a fresh container
target = DockerTarget(
    DockerConfig(container_name="hop3-test"),
    deployment=DeploymentConfig(source="local"),
)

# Connect to an existing container (skip deploy, iterate on verification)
target = DockerTarget(
    DockerConfig(container_name="hop3-test", reuse_container=True),
)
```

`DockerConfig` defaults to `image="debian:bookworm"` and `container_name="hop3-test"`. The target manages the container lifecycle and the SSH key extraction needed to drive `hop3-deploy-server`.

### Remote Target

`RemoteTarget` (`targets/remote.py`) runs tests against a remote Hop3 server over SSH (via paramiko), configured through a `RemoteConfig` dataclass:

```python
from hop3_testing.targets import RemoteTarget, RemoteConfig, DeploymentConfig

# Connect to an already-provisioned server
target = RemoteTarget(RemoteConfig(host="server.example.com"))

# Provision and deploy Hop3 from local code, cleaning first
target = RemoteTarget(
    RemoteConfig(host="server.example.com"),
    deployment=DeploymentConfig(source="local", clean=True),
)
```

`RemoteConfig` defaults to `port=22`, `user="root"`, and resolves `ssh_key` from configuration or the environment.

## Catalog

`Catalog` (`catalog/scanner.py`) discovers tests across the app and demo trees and indexes them by category, tier, and priority.

### What gets scanned

The scanner walks the test-app directories and reads each test's configuration:

```
apps/test-apps-procfile/   # Procfile-only apps (standalone test.toml)
apps/test-apps-nix/        # Nix-based test apps
apps/real-apps-native/     # Real apps, native toolchains
apps/real-apps-nix/        # Real apps, hand-crafted Nix
apps/real-apps-nix-gen/    # Real apps, Nix from template
demos/                     # Demo walkthroughs
docs/src/tutorials/        # Tutorial scripts
```

Each real app declares its test configuration under a `[test]` section in its own `hop3.toml`. Apps without a `hop3.toml` — Procfile-only test apps, demos, tutorials, and negative-test cases — keep a standalone `test.toml`.

### Test definition

The primary shape is a `[test]` section inside the app's `hop3.toml`. Most fields are derived from the rest of the file: the name from `[metadata].id`, the category from `[build].builder`, the services from `[[addons]]`, and the base healthcheck from `[healthcheck]`.

```toml
[metadata]
id = "flask-hello"

[build]
builder = "nix"

[healthcheck]
path = "/"

[test]
priority = "P0"                    # P0 | P1 | P2
tier = "fast"                      # report label only (no longer a timeout)
targets = ["docker", "remote"]
covers = ["python", "flask", "nix"]

[[test.validations]]
path = "/"
status = 200
contains = "Hello"
```

For Procfile-only apps, demos, tutorials, and negative-test cases (no `hop3.toml`), the legacy standalone `test.toml` is still supported:

```toml
[test]
name = "010-flask-pip-wsgi"
category = "deployment"
tier = "fast"
priority = "P0"

[test.requirements]
targets = ["docker", "remote"]
services = []

[[validations]]
type = "http"
path = "/"
[validations.expect]
status = 200
```

### Catalog API

```python
from hop3_testing.catalog import Catalog

catalog = Catalog(root)
catalog.scan(paths=["apps/test-apps-procfile", "demos"])

# Look up a single test by name
test = catalog.get_test("010-flask-pip-wsgi")

# Filter by tier / priority / tag
fast_p0 = catalog.filter(tiers=["fast"], priorities=["P0"])
```

`Tier` is one of `fast`, `medium`, `slow`, `very-slow` (a report label, no longer a timeout). `Priority` is one of `P0`, `P1`, `P2`.

## Deployment Sessions

`DeploymentSession` (`apps/deployment.py`) is a context manager that orchestrates the deploy/verify/cleanup lifecycle against a target:

```python
class DeploymentSession:
    """Orchestrates deploy / verify / cleanup for one app."""

    def __enter__(self) -> "DeploymentSession":
        return self

    def __exit__(self, *args) -> None:
        self.cleanup()

    def prepare(self) -> None:
        """Copy the app to a temp dir, initialize git, write the ENV file."""

    def deploy(self, wait_time: int = 5, deploy_timeout: int = 600) -> None:
        """Create the tarball and deploy via the hop3 CLI / RPC."""

    def check_deployed(self) -> bool:
        """Return True once the app reports as deployed."""

    def test_http_detailed(self) -> dict:
        """Verify the HTTP endpoint; returns {passed, message, details}."""

    def run_check_script_detailed(self) -> dict:
        """Run the app's check.py (if present) and return its result."""

    def cleanup(self) -> None:
        """Destroy the deployed app and its addon state."""
```

`__enter__` only arms cleanup; the caller drives `prepare()` and `deploy()` explicitly. `__exit__` always calls `cleanup()`.

Teardown goes through the target's `destroy_app`, which reaps the app's processes, releases its port, and removes its addon slots, so destroying one app never disturbs another.

## pytest Integration

Real deploy-and-verify tests live in the `c_e2e` layer (see [ADR 043](../adrs/043-unified-testing-architecture.md)). These tests need Docker and a real server, so they run out of process and are pass/fail (coverage is measured on `a_unit` + `b_integration` only). The `c_e2e` fixtures drive the same `DeploymentTarget` ABC the CLI uses.

### Fixtures

```python
# conftest.py
import pytest
from hop3_testing.targets import DockerTarget, DockerConfig, DeploymentConfig

@pytest.fixture(scope="session")
def deployment_target():
    """Provide a Docker target with Hop3 deployed from local code."""
    target = DockerTarget(
        DockerConfig(container_name="hop3-test"),
        deployment=DeploymentConfig(source="local"),
    )
    target.start()
    yield target
    target.stop()
```

### Example Test

```python
from pathlib import Path
from hop3_testing.apps import AppSource, DeploymentSession

def test_app_deployment(deployment_target):
    """Deploy an app and verify it responds."""
    app = AppSource(
        name="flask-hello",
        path=Path("apps/test-apps-procfile/010-flask-pip-wsgi"),
    )
    with DeploymentSession(app, deployment_target) as session:
        session.prepare()
        session.deploy()
        assert session.check_deployed()
        result = session.test_http_detailed()
        assert result["passed"]
```

## CLI Interface

The `hop3-test` CLI has four subcommands. The full flag reference for each is in the package [README](https://github.com/abilian/hop3) and `packages/hop3-testing/docs/internals.md`.

### `hop3-test run`

Deploys Hop3 to a target, then deploys the selected apps and verifies their HTTP responses.

```bash
# Deploy Hop3 + run the default tests on Docker
hop3-test run --docker

# Scan a specific directory
hop3-test run --docker apps/test-apps-procfile

# Run the full catalog with all addons, clean install
hop3-test run --docker --clean --with all

# Test one app, reusing the existing container (skip the Hop3 deploy)
hop3-test run --docker --reuse apps/real-apps-native/edrix

# Run against a remote server over SSH
hop3-test run --host server.example.com --clean --with all

# Fast P0-only profile
hop3-test run --docker --mode dev
```

Key options:

| Option | Description |
|--------|-------------|
| `--docker` / `--host` | Target type (Docker, or `--host` for a remote server) |
| `--host HOST` | Remote target server (or set `HOP3_TEST_HOST`) |
| `--from {local,git,pypi,none}` | Where to deploy Hop3 from (default `local`) |
| `--reuse` | Reuse the existing deployment (skip the Hop3 deploy) |
| `--clean` | Clean install (remove any existing installation first) |
| `--with FEATURE` | Install extra features/addons (`nix`, `mysql`, `redis`, `all`) |
| `--mode MODE` | Test profile (filters by tier/priority; e.g. `dev`, `smoke`, `ci`) |
| `--keep` | Keep the target and apps after the run |
| `-x, --fail-fast` | Stop on the first failure |
| `--report {none,text,html}` | Report format |

### `hop3-test list`

Discovers and displays available tests.

```bash
hop3-test list                                # All tests
hop3-test list apps/test-apps-procfile        # Scan one directory
hop3-test list demos -t fast                  # Fast demos only
hop3-test list --show 010-flask-pip-wsgi      # Details for one test
hop3-test list --format json                  # Machine-readable output
```

Filters: `-t/--tier`, `-p/--priority`, `--tag`. `--show NAME` prints the full definition of a single test.

### `hop3-test cloud`

Runs E2E tests on real cloud infrastructure (Hetzner). Requires the `HETZNER_API_TOKEN` environment variable.

```bash
hop3-test cloud --list-images                       # Available OS images
hop3-test cloud --image ubuntu-24.04                # Single distribution
hop3-test cloud --images ubuntu-24.04,debian-13     # Multiple distributions
hop3-test cloud --images all                        # All distributions
hop3-test cloud --apps apps/test-apps --apps demos  # Specific suites
hop3-test cloud --skip-reset --skip-deploy          # Only run tests
```

### `hop3-test why`

Replays the saved diagnostic bundle for a failed run (see ADR 043 §7). The `RUN_ID` is the `<ISO>-<app>-<shortid>` printed in a failure headline.

```bash
hop3-test why <run-id>                  # Headline + classification + bundle path
hop3-test why <run-id> --list           # List the bundle's sections
hop3-test why <run-id> --section proxy  # Replay the proxy-reachability probe
```

Available sections: `proxy`, `nginx`, `app`, `journal`, `build`, `deploy`, `http`, `dns`.

## Test Categories

Categories are derived from each app's builder and toolchain. The catalog covers, among others:

| Category | Languages/Frameworks |
|----------|----------------------|
| `python` | Flask, FastAPI, Django |
| `nodejs` | Express, Fastify |
| `ruby` | Sinatra, Rails |
| `go` | Fiber, Gin |
| `rust` | Actix-web, Axum |
| `static` | HTML, Hugo, Jekyll |
| `docker` | Dockerfile builds |
| `nix` | Nix-based builds |

## Validations

A test's expectations are expressed as `[[test.validations]]` entries (in `hop3.toml`) or `[[validations]]` entries (in a standalone `test.toml`). The most common form is an HTTP check:

```toml
[[test.validations]]
path = "/"
status = 200
contains = "Welcome"
```

Each validation hits a `path`, asserts a `status`, and can assert response body content (`contains`). For richer checks, an app can ship a `check.py` exposing a `check(hostname, port)` function, run via `run_check_script_detailed`. Asserting app-specific body content (not just a 200) is the gate before an app is advertised — a 200 can be a placeholder, an error page, or another app's content.

## Debugging

### Verbose output

`-v/--verbose` is a group-level flag, so it goes before the subcommand:

```bash
hop3-test -v run --docker
```

### Keep the target after a run

```bash
hop3-test run --docker --keep
# The container stays up for inspection:
docker exec -it hop3-test bash
```

### Reuse an existing deployment

```bash
# Iterate on verification against an already-deployed app, without redeploying Hop3
hop3-test run --docker --reuse apps/real-apps-native/edrix
```

### Replay a failure

When a run fails, copy the `RUN_ID` from the failure headline and replay its diagnostic bundle:

```bash
hop3-test why <run-id> --section proxy
```

The proxy section captures the silent-502 class (a healthy app behind a front-end 502 because the proxy points at the wrong port/host) that motivated the unified diagnostics in ADR 043.
