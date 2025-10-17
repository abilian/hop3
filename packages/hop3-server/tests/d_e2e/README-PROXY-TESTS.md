# E2E Proxy Plugin Tests

This directory contains end-to-end tests for all three proxy plugins (Nginx, Caddy, Traefik).

## Overview

The proxy plugin E2E tests verify that each proxy implementation can:
1. Configure virtual hosts correctly
2. Route HTTP traffic to deployed applications
3. Handle SSL/TLS certificates (with self-signed certs in test environment)
4. Integrate seamlessly with the pluggable architecture

## Test Structure

### Test File: `test_proxy_plugins.py`

**Three Test Classes:**
- `TestNginxProxyPlugin` - Tests Nginx proxy (default)
- `TestCaddyProxyPlugin` - Tests Caddy proxy
- `TestTraefikProxyPlugin` - Tests Traefik proxy

Each test class:
- Creates a separate Docker container with the specific proxy configured via `HOP3_PROXY_TYPE`
- Deploys a simple Flask application
- Verifies HTTP access through the proxy with virtual host routing
- Cleans up the deployment

### Container Configuration

Each proxy type gets its own container with:
```python
environment={
    "HOP3_PROXY_TYPE": "nginx"  # or "caddy" or "traefik"
}
```

The containers expose:
- Port 22 (SSH) - for CLI access
- Port 80 (HTTP) - for proxy testing
- Port 8000 (Hop3 server) - for RPC

## Prerequisites

### 1. Docker

Ensure Docker is running:
```bash
docker ps
```

### 2. Proxy Binaries in Docker Image

The Dockerfile (`docker/Dockerfile`) installs all three proxies:

- **Nginx**: Installed from Ubuntu 22.04 repository
- **Caddy**: Installed from official Caddy repository
- **Traefik**: Downloaded as static binary from GitHub releases

**Important Note:** The Docker image installs hop3-server **directly from source** using `pip install -e`. This means:
- ✅ No need to run `uv build` before testing
- ✅ Always tests the latest code changes
- ✅ Faster iteration during development
- ✅ No risk of forgetting to rebuild distribution

The image is built automatically on first test run and cached for subsequent runs.

## Running the Tests

### Run All Proxy Tests

```bash
# From project root
uv run pytest packages/hop3-server/tests/d_e2e/test_proxy_plugins.py -v -m e2e
```

### Run Individual Proxy Tests

```bash
# Test only Nginx
uv run pytest packages/hop3-server/tests/d_e2e/test_proxy_plugins.py::TestNginxProxyPlugin -v -m e2e

# Test only Caddy
uv run pytest packages/hop3-server/tests/d_e2e/test_proxy_plugins.py::TestCaddyProxyPlugin -v -m e2e

# Test only Traefik
uv run pytest packages/hop3-server/tests/d_e2e/test_proxy_plugins.py::TestTraefikProxyPlugin -v -m e2e
```

### Verbose Output

For detailed logs during test execution:
```bash
uv run pytest packages/hop3-server/tests/d_e2e/test_proxy_plugins.py -v -s -m e2e
```

The `-s` flag shows print statements, useful for debugging container startup and HTTP requests.

## What Each Test Does

### 1. Container Setup (per test class)

```python
@pytest.fixture(scope="class")
def proxy_container(self, docker_client, hop3_image):
    """Create container with specific proxy configured."""
    yield from create_proxy_container(docker_client, hop3_image, "nginx")
```

- Starts Docker container with `HOP3_PROXY_TYPE` environment variable
- Waits for hop3-server to be ready (up to 60 seconds)
- Extracts SSH key for CLI access
- Yields container info to tests

### 2. Application Deployment

```python
def _test_proxy_deployment(self, container_info, test_app_dir):
    # 1. Create Flask app
    (test_app_dir / "app.py").write_text(...)

    # 2. Create requirements.txt and Procfile

    # 3. Configure virtual host
    (test_app_dir / "env").write_text("HOST_NAME=app.test.local")

    # 4. Deploy via RPC
    client.rpc("cli", ["deploy", app_name], repository=tarball_b64)
```

### 3. HTTP Verification

```python
# Test with Host header (virtual host routing)
response = httpx.get(
    f"http://localhost:{http_port}/",
    headers={"Host": f"{app_name}.test.local"},
    timeout=2.0,
)

assert response.status_code == 200
assert f"Hello from {proxy_type.upper()} proxy" in response.text
```

- Uses virtual host routing (HTTP Host header)
- Retries up to 30 times (uWSGI vassal needs time to start)
- Verifies correct response from application

### 4. Cleanup

```python
# Destroy application
container.exec_run(f"su - hop3 -c '~/venv/bin/hop-server destroy {app_name}'")

# Container automatically removed after test class finishes
```

## Troubleshooting

### Test Timeout: Container Won't Start

If container fails to start within 60 seconds:

1. Check Docker logs:
```python
container.logs().decode()
```

2. Check hop3-server logs inside container:
```bash
docker exec <container-id> cat /var/log/supervisor/hop3-server.log
docker exec <container-id> cat /var/log/supervisor/hop3-server_err.log
```

3. Manually inspect container:
```bash
# Find container ID
docker ps

# Enter container
docker exec -it <container-id> bash

# Check services
supervisorctl status
```

### HTTP Test Fails: Backend Not Ready (502)

The test retries 30 times with 1-second intervals. If all attempts fail:

1. **uWSGI vassal not starting**: Check if uWSGI is running
```bash
docker exec <container-id> ps aux | grep uwsgi
```

2. **Wrong socket path**: Verify socket exists
```bash
docker exec <container-id> ls -la /tmp/*.sock
```

3. **Proxy misconfiguration**: Check proxy config files
```bash
# Nginx
docker exec <container-id> cat /home/hop3/nginx/*.conf

# Caddy
docker exec <container-id> cat /home/hop3/caddy/*.caddyfile

# Traefik
docker exec <container-id> cat /etc/traefik/dynamic/*.yml
```

### Proxy Binary Not Found

If a proxy binary is missing, rebuild the Docker image:

```bash
# Remove old image
docker rmi hop3-e2e:test

# Rebuild will happen automatically on next test run
uv run pytest packages/hop3-server/tests/d_e2e/test_proxy_plugins.py -v -m e2e
```

### Port Conflicts

If ports are already in use:
```bash
# Find processes using port 80
lsof -i :80

# Docker maps to random ports, so this should rarely be an issue
```

## Test Duration

- **Container startup**: ~10-15 seconds
- **Application deployment**: ~15-20 seconds
- **HTTP verification**: ~1-30 seconds (depending on uWSGI startup)

**Total per proxy test**: ~40-60 seconds

**All three proxies**: ~2-3 minutes

## CI/CD Integration

These tests are suitable for CI/CD pipelines with Docker support.

### GitHub Actions Example

```yaml
name: E2E Proxy Tests

on: [push, pull_request]

jobs:
  test-proxies:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        proxy: [nginx, caddy, traefik]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install uv
        run: pip install uv

      - name: Build distribution
        run: uv build packages/hop3-server

      - name: Run ${{ matrix.proxy }} tests
        run: |
          uv run pytest \
            packages/hop3-server/tests/d_e2e/test_proxy_plugins.py::Test${matrix.proxy^}ProxyPlugin \
            -v -m e2e
```

## Known Issues

### SSH Tunnel Connection Refused (Current)

The E2E tests currently fail during the deployment step with:

```
ConnectionError: HTTPConnectionPool(host='localhost', port=8000): Max retries exceeded
(Caused by: Failed to establish a new connection: [Errno 61] Connection refused')
```

**Root Cause**: The CLI client tries to establish an SSH tunnel to deploy the app, but the tunnel creation is failing in the test environment.

**Status**: Infrastructure is working (container starts, hop3-server responds), but SSH tunneling needs debugging.

**Workaround**: Manual testing by:
1. Starting a container with specific proxy type
2. SSH into the container
3. Deploy directly via `hop-server deploy` command inside the container

## Future Enhancements

- [ ] Fix SSH tunnel creation in E2E tests
- [ ] Test SSL/TLS certificate generation (currently using `ACME_ENGINE=self-signed`)
- [ ] Test static file serving through each proxy
- [ ] Test WebSocket proxying
- [ ] Test custom proxy configuration per application
- [ ] Performance comparison between proxy types
- [ ] Load testing with multiple concurrent requests

## Related Documentation

- [ADR-071: Proxy Plugin System](../../../../../notes/adrs/071-proxy-plugin-system.md)
- [ADR-070: Pluggable Architecture](../../../../../notes/adrs/070-pluggable-architecture.md)
- [Main E2E Test Documentation](./README.md) (if exists)
