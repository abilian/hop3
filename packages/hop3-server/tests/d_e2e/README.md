# E2E Tests

End-to-end tests that deploy applications to a Hop3 environment (Docker container or remote server).

## Prerequisites

Docker must be installed and running.

## Running Tests

```bash
# Run all E2E tests (Docker target by default)
uv run pytest packages/hop3-server/tests/d_e2e/ -v

# Run specific test
uv run pytest packages/hop3-server/tests/d_e2e/test_simple_apps.py -v

# Run against a remote server
uv run pytest packages/hop3-server/tests/d_e2e/ -v --host my-server.com

# Keep container running after tests (for debugging)
uv run pytest packages/hop3-server/tests/d_e2e/ -v --keep-target

# Skip E2E tests
uv run pytest -m "not e2e"
```

## Command-Line Options

| Option | Description |
|--------|-------------|
| `--host HOST` | Use remote target instead of Docker |
| `--ssh-key PATH` | SSH key for remote target |
| `--keep-target` | Keep Docker container running after tests |
| `--force-rebuild` | Force rebuild of Docker image |
| `--use-cache` | Use existing Docker image, skip build |

## Writing Tests

Tests use `DeploymentSession` from `hop3-testing`:

```python
import pytest
from hop3_testing.apps import DeploymentSession
from hop3_testing.apps.catalog import AppSource


@pytest.mark.e2e
def test_my_app(deployment_target, tmp_path):
    app = AppSource(name="my-app", path=tmp_path / "my-app")

    with DeploymentSession(app, deployment_target) as session:
        session.deploy()  # Raises DeploymentError on failure
        assert session.check_deployed()
        assert session.test_http()
```

The `deployment_target` fixture (from `conftest.py`) manages the Docker container or remote connection.

## Test Structure

```
tests/d_e2e/
├── conftest.py              # Pytest fixtures (target management)
├── test_simple_apps.py      # Deploy apps from apps/test-apps/
├── test_backup.py           # Backup/restore tests
├── test_full_deployment.py  # Deployment lifecycle tests
├── test_proxy_plugins.py    # Proxy configuration tests
└── README.md
```

## Debugging

```bash
# List running containers
docker ps

# View container logs
docker logs <container-id>

# SSH into container
ssh -i /tmp/hop3-key-xxx -p <port> hop3@localhost

# Check hop3-server status
docker exec <container-id> systemctl status hop3-server

# View hop3 logs
docker exec <container-id> journalctl -u hop3-server -n 50
```

## Cleanup

```bash
# Stop all hop3 test containers
docker ps -a | grep hop3 | awk '{print $1}' | xargs docker stop

# Remove containers
docker ps -a | grep hop3 | awk '{print $1}' | xargs docker rm
```
