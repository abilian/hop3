# Full End-to-End Tests (Docker-Based)

This directory contains full end-to-end tests that deploy real applications in isolated Docker containers with systemd, nginx, uwsgi, and all production dependencies.

## Prerequisites

1. **Docker** must be installed and running:
   ```bash
   docker --version
   docker info
   ```


## Quick Start

```bash
# Build the E2E test image (first time only, ~5-10 minutes)
pytest packages/hop3-server/tests/d_e2e/ --setup-show

# Run all E2E tests
pytest packages/hop3-server/tests/d_e2e/ -v

# Run specific test
pytest packages/hop3-server/tests/d_e2e/test_python_deployment.py::TestPythonFlaskDeployment::test_deploy_simple_flask_app -v -s
```

## Architecture

### Container Environment

Each test class gets a fresh container with:
- **Operating System**: Ubuntu 22.04
- **Init System**: systemd (for realistic service management)
- **Web Server**: nginx (configured but not always used)
- **App Server**: uwsgi
- **Database**: PostgreSQL
- **Hop3 Server**: Fully installed and running
- **SSH Access**: Configured for hop3 user

### Test Flow

```
┌──────────────────────────────────────────────────────────────┐
│ 1. Build Docker Image (session scope, once per run)          │
│    - Build hop3-server distribution                          │
│    - Create Docker image with systemd                        │
│    - Install hop3 and all dependencies                       │
└────────────────┬─────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────┐
│ 2. Start Container (class scope, once per test class)        │
│    - Start container with systemd                            │
│    - Wait for services (hop3-server, postgresql, ssh)        │
│    - Extract connection details (ports, SSH key)             │
└────────────────┬─────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────┐
│ 3. Run Tests (function scope)                                │
│    - Create test application                                 │
│    - Deploy using hop3 CLI                                   │
│    - Verify deployment                                       │
│    - Test HTTP endpoints                                     │
│    - Clean up application                                    │
└────────────────┬─────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────┐
│ 4. Stop Container (automatic cleanup)                        │
│    - Stop systemd gracefully                                 │
│    - Remove container                                        │
│    - Clean up SSH keys                                       │
└──────────────────────────────────────────────────────────────┘
```

## Test Structure

```
tests/d_e2e/
├── docker/
│   ├── Dockerfile          # Container image definition
│   └── .dockerignore       # Build context exclusions
├── conftest.py             # Pytest fixtures (container management)
├── test_full_deployment.py     # Full infrastructure tests (lifecycle, env vars, etc.)
├── test_python_deployment.py   # Python app tests
├── test_proxy_plugins.py       # Proxy plugin tests (nginx, caddy, traefik)
├── test_nodejs_deployment.py   # Node.js app tests (future)
├── test_ruby_deployment.py     # Ruby app tests (future)
└── README.md               # This file
```

### Test Files

- **test_full_deployment.py**: Full deployment lifecycle tests (uwsgi, nginx, systemd):
  - Application lifecycle (start, stop, restart, status)
  - Environment variable management (config:set, config:get, config:unset)
  - Application destruction and cleanup
  - Web endpoint accessibility
  - Git-hook deployment workflow
  - Uses Docker containers (via `hop3_container` fixture)
  - Helper function `deploy_flask_app()` for common deployment pattern

- **test_python_deployment.py**: Python application deployment tests
  - Flask deployment with various configurations
  - Django deployment (TODO)
  - Package management (pip, poetry, pipenv)
  - Uses Docker containers (via `hop3_container` fixture)

- **test_proxy_plugins.py**: Proxy plugin tests
  - nginx proxy configuration
  - caddy proxy configuration (TODO)
  - traefik proxy configuration (TODO)
  - Uses Docker containers (via `hop3_container` fixture)

## Writing E2E Tests

### Basic Test Template

```python
import pytest
import time
from pathlib import Path

@pytest.mark.e2e
class TestMyDeployment:
    """Test deploying my application type."""

    def test_deploy_my_app(self, hop3_container, hop3_command, test_app_dir):
        """Test deploying my app."""
        app_name = f"my-app-{int(time.time())}"

        # 1. Create application files
        (test_app_dir / "app.py").write_text("...")
        (test_app_dir / "requirements.txt").write_text("...")
        (test_app_dir / "Procfile").write_text("...")

        # 2. Initialize git
        subprocess.run(["git", "init"], cwd=test_app_dir, check=True)
        subprocess.run(["git", "add", "."], cwd=test_app_dir, check=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=test_app_dir, check=True)

        # 3. Deploy
        result = hop3_command("deploy", app_name, str(test_app_dir))
        assert result.returncode == 0

        # 4. Verify
        result = hop3_command("apps")
        assert app_name in result.stdout

        # 5. Cleanup
        hop3_command("destroy", app_name)
```

### Available Fixtures

#### `hop3_container` (class scope)
Provides a running container with connection details:
```python
{
    "container": docker.Container,  # Docker container object
    "ssh_host": "hop3@localhost",   # SSH connection string
    "ssh_port": 12345,              # SSH port
    "ssh_key": "/tmp/hop3-key-...", # Path to SSH key
    "http_base": "http://localhost:8080",  # HTTP base URL
    "api_url": "http://localhost:8000",    # Hop3 API URL
}
```

#### `hop3_command` (function scope)
Helper function to run hop3 CLI commands:
```python
result = hop3_command("apps")  # Returns subprocess.CompletedProcess
result = hop3_command("deploy", "myapp", "/path/to/app")
result = hop3_command("destroy", "myapp")
```

#### `test_app_dir` (function scope)
Temporary directory for creating test applications:
```python
(test_app_dir / "app.py").write_text("...")
(test_app_dir / "requirements.txt").write_text("...")
```

## Running Tests

### Run All E2E Tests
```bash
pytest packages/hop3-server/tests/d_e2e/ -v
```

### Run Specific Test Class
```bash
pytest packages/hop3-server/tests/d_e2e/test_python_deployment.py::TestPythonFlaskDeployment -v
```

### Run Single Test
```bash
pytest packages/hop3-server/tests/d_e2e/test_python_deployment.py::TestPythonFlaskDeployment::test_deploy_simple_flask_app -v -s
```

### Run with Detailed Output
```bash
pytest packages/hop3-server/tests/d_e2e/ -v -s --log-cli-level=INFO
```

### Skip E2E Tests
```bash
pytest -m "not e2e"
```

## Container Management

### Manually Start Container for Debugging
```python
# In Python shell
import docker
client = docker.from_env()
container = client.containers.run(
    "hop3-e2e:test",
    detach=True,
    privileged=True,
    ports={"22/tcp": 2222, "8000/tcp": 8000}
)

# Get SSH key
result = container.exec_run("cat /home/hop3/.ssh/id_rsa")
print(result.output.decode())

# SSH into container
# ssh -i /path/to/key -p 2222 hop3@localhost
```

### Inspect Running Container
```bash
# List running containers
docker ps

# View logs
docker logs <container-id>

# Execute command in container
docker exec -it <container-id> bash

# Check hop3-server service
docker exec <container-id> systemctl status hop3-server

# View hop3 logs
docker exec <container-id> journalctl -u hop3-server -n 50
```

### Clean Up

```bash
# Stop all hop3-e2e containers
docker ps -a | grep hop3-e2e | awk '{print $1}' | xargs docker stop

# Remove containers
docker ps -a | grep hop3-e2e | awk '{print $1}' | xargs docker rm

# Remove images
docker images | grep hop3-e2e | awk '{print $3}' | xargs docker rmi
```

## Troubleshooting

### Image Build Fails

**Issue**: Docker build fails with "dist/hop3_server-*.tar.gz not found"

**Solution**: Build the distribution first:
```bash
uv build packages/hop3-server
```

### Container Won't Start

**Issue**: Container starts but services don't come up

**Debug**:
```bash
# Check systemd logs
docker exec <container-id> journalctl -xe

# Check specific service
docker exec <container-id> systemctl status hop3-server
docker exec <container-id> systemctl status postgresql
```

### Tests Timeout

**Issue**: Tests hang waiting for services

**Possible Causes**:
1. Services taking too long to start (increase timeout)
2. Service failed to start (check logs)
3. Port conflicts (Docker can't allocate random ports)

**Debug**:
```bash
# Check if ports are bound
docker ps
netstat -tulpn | grep LISTEN

# Check container logs
docker logs <container-id>
```

### SSH Connection Fails

**Issue**: Can't SSH into container

**Debug**:
```bash
# Check SSH service
docker exec <container-id> systemctl status ssh

# Check SSH key permissions
docker exec <container-id> ls -la /home/hop3/.ssh/

# Try manual SSH
ssh -i /tmp/hop3-e2e-key-<id> -p <port> -v hop3@localhost
```

## Performance Considerations

### Build Time
- **First build**: 5-10 minutes (installs all dependencies)
- **Subsequent builds**: 1-2 minutes (Docker cache)
- **With changes**: 2-5 minutes (partial rebuild)

### Container Startup
- **Cold start**: 10-15 seconds (systemd init + services)
- **Warm start**: 5-10 seconds (services only)

### Test Execution
- **Single test**: 30-60 seconds
- **Full test class**: 2-5 minutes
- **All E2E tests**: 10-20 minutes

### Optimization Tips

1. **Use class scope for container**: Tests in same class share container
2. **Cache Docker image**: Build once, use many times
3. **Parallel test execution**: Run test classes in parallel (future)
4. **Skip in development**: Use `-m "not e2e"` for fast iteration

## CI Integration

### GitHub Actions Example

```yaml
name: E2E Tests

on: [push, pull_request]

jobs:
  e2e:
    runs-on: ubuntu-latest
    timeout-minutes: 30

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install uv
          uv sync
          uv build packages/hop3-server

      - name: Run E2E tests
        run: |
          uv run pytest packages/hop3-server/tests/d_e2e/ \
            -v \
            --log-cli-level=INFO \
            --junit-xml=junit-e2e.xml

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: e2e-test-results
          path: junit-e2e.xml
```

## Future Enhancements

- [ ] Add Node.js deployment tests
- [ ] Add Ruby deployment tests
- [ ] Add Go deployment tests
- [ ] Add database service attachment tests
- [ ] Add nginx configuration tests
- [ ] Add SSL/TLS certificate tests
- [ ] Add scaling/worker tests
- [ ] Add backup/restore tests
- [ ] Add parallel test execution
- [ ] Add container snapshot/restore for faster tests
