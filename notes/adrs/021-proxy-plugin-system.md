# ADR 021: Proxy Plugin System for Reverse Proxy Configuration

- **Status**: Final
- **Type**: Feature
- **Created**: 2024-10-01
- **Related-ADRs**: 020, 022, 023

## Context

The original Hop3 architecture hardcoded Nginx as the reverse proxy, making it impossible to use alternatives like Caddy or Traefik without modifying core code. With the pluggable architecture (ADR-020), proxy configuration became the third stage in the deployment pipeline, but with a critical architectural constraint: **there is only one reverse proxy for an entire server**.

## Decision

We implement proxy configuration as a plugin system with **server-wide configuration**:

1. **Server-Wide Selection:** Proxy type is set via `HOP3_PROXY_TYPE` environment variable (server config), not per-application
2. **Proxy Protocol:** A Python `Protocol` defines the interface with `setup(app, env, workers)` method
3. **Plugin Discovery:** Proxies are discovered via `get_proxies()` hookspec
4. **Three Implementations:**
   - **Nginx** (default) — ACME certificates, static file serving, caching, IPv4/IPv6
   - **Caddy** — automatic HTTPS, simpler configuration, modern features
   - **Traefik** — cloud-native, dynamic configuration, service discovery

## Proxy Plugin Interface

### Protocol Definition

```python
class Proxy(Protocol):
    """Protocol for reverse proxy configuration strategies.

    A proxy is responsible for configuring the reverse proxy server
    (Nginx, Caddy, Traefik, etc.) to route HTTP(S) traffic to
    deployed applications.
    """

    app: App              # Application being configured
    env: Env              # Application environment variables
    workers: dict[str, str]  # Worker name -> socket path mapping

    def setup(self) -> None:
        """Configure the proxy for this application.

        Implementations must:
        1. Generate proxy configuration files
        2. Configure SSL/TLS certificates (ACME/Let's Encrypt)
        3. Set up static file serving if needed
        4. Reload/restart the proxy server

        Side effects:
        - Writes configuration files to proxy config directory
        - May request SSL certificates from ACME provider
        - Reloads proxy server (graceful reload, no downtime)

        Raises:
            RuntimeError: If proxy configuration fails
            FileNotFoundError: If required files missing
        """
```

### Input Specifications

**`app: App`** - The application being configured:
- `app.name` - Application identifier (used in config filenames)
- `app.app_path` - Application directory path
- `app.state` - Current application state

**`env: Env`** - Application environment variables:
- `HOST_NAME` - Primary domain(s) for this app (comma-separated)
- `NGINX_STATIC_PATHS` - Static file paths to serve directly
- `NGINX_CLOUDFLARE_CERT` - Enable Cloudflare Origin certificates
- Additional proxy-specific environment variables

**`workers: dict[str, str]`** - Worker processes:
```python
{
    "web": "/tmp/myapp.sock",        # Web worker socket
    "api": "/tmp/myapp-api.sock",    # API worker socket
}
```

### Output and Side Effects

**Configuration Files Created:**
- Nginx: `HOP3_ROOT/nginx/{app_name}.conf`
- Caddy: `HOP3_ROOT/caddy/{app_name}.caddyfile`
- Traefik: `HOP3_ROOT/traefik/dynamic/{app_name}.yml`

**SSL/TLS Certificates:**
- Automatic certificate requests via ACME protocol
- Certificates stored in proxy-specific cert directory
- Automatic renewal managed by proxy

**Server Reload:**
- Graceful reload (no dropped connections)
- Configuration validation before reload
- Rollback on validation failure

## Plugin Registration

```python
from hop3.core.hooks import hookimpl

class NginxProxyPlugin:
    """Nginx reverse proxy plugin for Hop3."""

    name = "nginx"

    @hookimpl
    def get_proxies(self) -> list:
        """Return list of proxy strategy classes."""
        return [NginxVirtualHost]

# Auto-register when module imported
plugin = NginxProxyPlugin()
```

## Configuration

### Server-Wide Configuration

Proxy type is set via environment variable in server configuration:

```bash
# /etc/hop3/server.conf or export in shell
export HOP3_PROXY_TYPE=nginx    # Default
export HOP3_PROXY_TYPE=caddy
export HOP3_PROXY_TYPE=traefik
```

### Per-Application Configuration

Applications configure proxy behavior via environment variables in their `ENV` file:

```bash
# Application ENV file
HOST_NAME=example.com,www.example.com
NGINX_STATIC_PATHS=/static:/media
NGINX_CLOUDFLARE_CERT=1
```

## Example: Nginx Plugin

```python
@dataclass(frozen=True)
class NginxVirtualHost:
    """Nginx reverse proxy implementation."""

    app: App
    env: Env
    workers: dict[str, str]

    def setup(self) -> None:
        """Configure Nginx for this application."""
        server_name = self.env["HOST_NAME"]

        # 1. Generate upstream backends configuration
        upstream_config = self._generate_upstream(self.workers)

        # 2. Configure SSL/TLS certificates
        cert_path = self._setup_acme_certificates(server_name)

        # 3. Generate main server block
        server_config = self._generate_server_block(
            server_name=server_name,
            cert_path=cert_path,
            upstream="app_upstream",
            static_paths=self.env.get("NGINX_STATIC_PATHS", ""),
        )

        # 4. Write configuration file
        config_file = HOP3_ROOT / "nginx" / f"{self.app.name}.conf"
        config_file.write_text(upstream_config + server_config)

        # 5. Validate and reload Nginx
        run(["nginx", "-t"])  # Validate config
        run(["nginx", "-s", "reload"])  # Graceful reload

    def _generate_upstream(self, workers: dict[str, str]) -> str:
        """Generate upstream block for uWSGI sockets."""
        return f"""
upstream app_upstream {{
    server unix:{workers['web']};
}}
"""

    def _setup_acme_certificates(self, domains: str) -> Path:
        """Request/renew SSL certificates via ACME."""
        # Implementation uses acme-tiny or similar
        return Path("/etc/letsencrypt/live/example.com/fullchain.pem")

    def _generate_server_block(self, **kwargs) -> str:
        """Generate Nginx server block from template."""
        # Template rendering logic
        return """
server {
    listen 80;
    listen [::]:80;
    server_name example.com;

    location / {
        include uwsgi_params;
        uwsgi_pass app_upstream;
    }
}
"""
```

## Selection and Usage

The `get_proxy_strategy()` helper function selects the configured proxy:

```python
def get_proxy_strategy(app: App, env: Env, workers: dict[str, str]) -> Proxy:
    """Find and instantiate the appropriate proxy strategy.

    The proxy type is determined by HOP3_PROXY_TYPE environment variable.

    Args:
        app: Application to configure
        env: Application environment
        workers: Worker name -> socket path mapping

    Returns:
        Proxy instance ready to call setup()

    Raises:
        RuntimeError: If configured proxy type not found
    """
    from hop3.config import HOP3_PROXY_TYPE

    pm = get_plugin_manager()
    strategies = pm.hook.get_proxies()

    for strategy_class in flatten(strategies):
        if HOP3_PROXY_TYPE in strategy_class.__name__.lower():
            return strategy_class(app, env, workers)

    raise RuntimeError(f"Proxy type '{HOP3_PROXY_TYPE}' not found")

# Usage in deployment
proxy = get_proxy_strategy(app, env, workers)
proxy.setup()
```

## Rationale

### Why Server-Wide (Not Per-Application)?

A server runs **one reverse proxy instance** listening on ports 80/443:

- **Physical Constraint:** Only one process can bind to port 80/443
- **Simplicity:** No need to manage multiple proxy instances or port routing
- **Performance:** Single proxy instance is more efficient
- **Operations:** Simpler to manage and monitor a single service

**Alternative Rejected:** Per-application proxy selection would require:
- Multiple proxy instances on different ports (requires meta-proxy for port 80/443)
- Complex port routing layer
- Significant operational complexity for negligible benefit

### Why Protocol Over ABC?

- **Structural Typing:** Duck typing is more Pythonic
- **Better IDE Support:** Type checkers understand Protocol better
- **No Inheritance Required:** Implementations don't need base class
- **Easier Testing:** Simpler to mock in tests

## Consequences

### Benefits

1. **Operator Choice:** Choose preferred reverse proxy (Nginx, Caddy, Traefik)
2. **Clean Architecture:** Server-wide config matches operational reality
3. **Extensibility:** New proxies added as plugins without core changes
4. **Backward Compatible:** Nginx remains default
5. **Consistent Interface:** All proxies implement same protocol

### Drawbacks

1. **Server-Wide Limitation:** Cannot mix proxies on same server (intentional constraint)
2. **Configuration Complexity:** Each proxy has different syntax/features
3. **Feature Parity:** Not all proxies support identical features

### Trade-offs Considered

| Aspect | Decision | Alternative | Why Rejected |
|--------|----------|-------------|--------------|
| **Scope** | Server-wide | Per-application | Physical constraint (port 80/443) |
| **Selection** | Explicit config | Auto-detection | Predictability over magic |
| **Interface** | Protocol | ABC | Structural typing more Pythonic |

## Prior Art

- **Heroku Routers:** Single router/proxy handles all applications
- **Kubernetes Ingress:** Cluster-wide ingress controller with per-service routing
- **Cloud Load Balancers:** AWS ALB, GCP LB - single instance routes to backends

## References

- [ADR-020: Pluggable Architecture](./020-pluggable-architecture.md)
- [ADR-022: Build and Deployment Plugin System](./022-build-deploy-plugin-system.md)
- [Python Protocol (PEP 544)](https://peps.python.org/pep-0544/)
