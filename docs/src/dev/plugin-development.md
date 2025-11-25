# Plugin Development Guide

This guide covers how to create plugins for Hop3 to extend its functionality with new build strategies, deployment runtimes, services, proxies, and operating system support.

## Overview

Hop3 uses a plugin-based architecture built on [pluggy](https://pluggy.readthedocs.io/), the same plugin framework used by pytest. Plugins allow you to extend Hop3 with:

- **Build Strategies**: Convert source code into runnable artifacts (e.g., Python buildpack, Docker builder)
- **Deployment Strategies** (Runtimes): Run build artifacts (e.g., uWSGI, Docker Compose, systemd)
- **Service Strategies**: Manage backing services like databases and caches (e.g., PostgreSQL, Redis, MySQL)
- **Proxy Strategies**: Configure reverse proxies (e.g., Nginx, Caddy, Traefik)
- **OS Setup Strategies**: Support different Linux distributions (e.g., Debian, Ubuntu, RHEL)

## When to Create a Plugin

Create a plugin when you want to:

- **Add support for a new programming language** (build strategy)
- **Support a new deployment method** (deployment strategy/runtime)
- **Integrate a new service** like MySQL, MongoDB, Elasticsearch (service strategy)
- **Add support for a new reverse proxy** (proxy strategy)
- **Support a new Linux distribution** (OS setup strategy)

Modify core code when you need to:

- Change the plugin system itself
- Modify the deployment pipeline orchestration
- Change database models or API contracts
- Update the CLI or web UI

## Plugin Types

### 1. Build Strategies

Build strategies convert source code into deployable artifacts.

**Protocol**: `Builder` (from `hop3.core.protocols`)

**Required attributes**:
- `name` (str): Unique identifier (e.g., "python", "docker")
- `context` (DeploymentContext): Deployment context with app info

**Required methods**:
- `accept() -> bool`: Return `True` if this strategy can build the app
- `build() -> BuildArtifact`: Execute build and return artifact info

**Example** (simplified Python builder):

```python
from pathlib import Path
from hop3.core.protocols import Builder, BuildArtifact, DeploymentContext


class PythonBuildStrategy:
    """Build Python applications using virtualenv."""

    name = "python"

    def __init__(self, context: DeploymentContext):
        self.context = context

    def accept(self) -> bool:
        """Accept if requirements.txt or pyproject.toml exists."""
        src_path = self.context.source_path
        return (src_path / "requirements.txt").exists() or
            (src_path / "pyproject.toml").exists()

    def build(self) -> BuildArtifact:
        """Create virtualenv and install dependencies."""
        app_name = self.context.app_name
        venv_path = Path(f"/home/hop3/apps/{app_name}/venv")

        # Create virtualenv
        subprocess.run(["python3", "-m", "venv", str(venv_path)], check=True)

        # Install dependencies
        pip = venv_path / "bin" / "pip"
        subprocess.run([str(pip), "install", "-r", "requirements.txt"],
                       cwd=self.context.source_path, check=True)

        return BuildArtifact(
            kind="virtualenv",
            location=str(venv_path),
            metadata={"python_version": "3.11"}
        )
```

### 2. Deployment Strategies (Runtimes)

Deployment strategies run build artifacts and manage their lifecycle.

**Protocol**: `Deployer` (from `hop3.core.protocols`)

**Required attributes**:
- `name` (str): Unique identifier (e.g., "uwsgi", "docker-compose")
- `context` (DeploymentContext): Deployment context
- `artifact` (BuildArtifact): Build artifact to deploy

**Required methods**:
- `accept() -> bool`: Return `True` if this strategy can deploy the artifact
- `deploy(deltas: dict | None = None) -> DeploymentInfo`: Deploy the artifact
- `stop() -> None`: Stop the running application
- `check_status() -> bool`: Check if app is actually running
- `scale(deltas: dict[str, int] | None = None) -> None`: Scale workers

**Example** (simplified Docker Compose deployer):

```python
import subprocess
from hop3.core.protocols import Deployer, DeploymentInfo

class DockerComposeDeployer:
    """Deploy applications using Docker Compose."""

    name = "docker-compose"

    def __init__(self, context, artifact):
        self.context = context
        self.artifact = artifact

    def accept(self) -> bool:
        """Accept if artifact is a docker-image."""
        return self.artifact.kind == "docker-image"

    def deploy(self, deltas=None) -> DeploymentInfo:
        """Run docker-compose up."""
        src_path = self.context.source_path

        env = {"HOP3_IMAGE_TAG": self.artifact.location}
        subprocess.run(
            ["docker", "compose", "up", "-d", "--remove-orphans"],
            cwd=src_path,
            check=True,
            env=env
        )

        return DeploymentInfo(
            protocol="http",
            address="127.0.0.1",
            port=8080
        )

    def stop(self):
        """Run docker-compose down."""
        src_path = self.context.source_path
        subprocess.run(["docker", "compose", "down"], cwd=src_path)

    def check_status(self) -> bool:
        """Check if containers are running."""
        result = subprocess.run(
            ["docker", "compose", "ps", "--format", "{{.State}}"],
            cwd=self.context.source_path,
            capture_output=True,
            text=True
        )
        return "running" in result.stdout.lower()

    def scale(self, deltas=None):
        """Scale services."""
        if not deltas:
            return

        scale_args = []
        for service, count in deltas.items():
            scale_args.extend(["--scale", f"{service}={count}"])

        cmd = ["docker", "compose", "up", "-d"] + scale_args
        subprocess.run(cmd, cwd=self.context.source_path, check=True)
```

### 3. Service Strategies

Service strategies manage backing services (databases, caches, etc.).

**Protocol**: `Addon` (from `hop3.core.protocols`)

**Required attributes**:
- `name` (str): Service type (e.g., "postgres", "redis")
- `service_name` (str): Specific instance name

**Required methods**:
- `create() -> None`: Create the service instance
- `destroy() -> None`: Destroy the service instance
- `get_connection_details() -> dict[str, str]`: Return environment variables for connection
- `backup() -> Path`: Create a backup
- `restore(backup_path: Path) -> None`: Restore from backup
- `info() -> dict`: Get service information

**Example** (simplified Redis service):

```python
from pathlib import Path
from hop3.core.protocols import Addon


class RedisService:
    """Manage Redis service instances."""

    name = "redis"

    def __init__(self, service_name: str):
        self.service_name = service_name

    def create(self):
        """Create Redis instance."""
        port = self._allocate_port()
        config_path = Path(f"/home/hop3/services/redis/{self.service_name}.conf")

        # Write Redis config
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(f"port {port}\nbind 127.0.0.1\n")

        # Start Redis with systemd
        subprocess.run([
            "systemctl", "start", f"redis-{self.service_name}"
        ], check=True)

    def destroy(self):
        """Destroy Redis instance."""
        subprocess.run([
            "systemctl", "stop", f"redis-{self.service_name}"
        ])

    def get_connection_details(self) -> dict[str, str]:
        """Return connection environment variables."""
        port = self._get_port()
        return {
            "REDIS_URL": f"redis://127.0.0.1:{port}/0"
        }

    def backup(self) -> Path:
        """Backup Redis data."""
        # Trigger BGSAVE and copy RDB file
        subprocess.run(["redis-cli", "BGSAVE"])
        # ... implementation details
        return Path(f"/backups/redis-{self.service_name}.rdb")

    def restore(self, backup_path: Path):
        """Restore from backup."""
        # Stop Redis, copy RDB file, restart
        # ... implementation details
        pass

    def info(self) -> dict:
        """Get service info."""
        return {
            "status": "running",
            "version": "7.0",
            "port": self._get_port()
        }
```

### 4. Proxy Strategies

Proxy strategies configure reverse proxies for applications.

**Base Class**: `BaseProxy` (from `hop3.core.protocols`)

**Required attributes**:
- `app` (App): Application instance
- `env` (Env): Environment variables
- `workers` (dict[str, str]): Worker configurations

**Required methods** (abstract):
- `get_proxy_name() -> str`: Return proxy name ("nginx", "caddy", "traefik")
- `setup_backend() -> None`: Configure backend connection
- `setup_certificates() -> None`: Setup SSL certificates
- `setup_cache() -> None`: Configure caching
- `setup_static() -> None`: Configure static file serving
- `extra_setup() -> None`: Additional proxy-specific setup
- `generate_config() -> None`: Generate proxy config file
- `check_config() -> None`: Validate config
- `reload_proxy() -> None`: Reload proxy to apply changes

**The `setup()` method is already implemented in BaseProxy** and orchestrates the setup process.

**Example** (simplified Nginx proxy):

```python
from dataclasses import dataclass
from hop3.core.protocols import BaseProxy

@dataclass(frozen=True)
class NginxVirtualHost(BaseProxy):
    """Nginx reverse proxy configuration."""

    def get_proxy_name(self) -> str:
        return "nginx"

    def setup_backend(self):
        """Configure backend connection."""
        # Use Unix socket or TCP
        if self.env.get("NGINX_SOCKET"):
            socket_path = f"/tmp/{self.app_name}.sock"
            self.update_env("NGINX_SOCKET", socket_path)
        else:
            port = self.app.port
            self.update_env("NGINX_BACKEND", f"127.0.0.1:{port}")

    def setup_certificates(self):
        """Setup SSL certificates."""
        # Generate self-signed cert or use Let's Encrypt
        pass

    def setup_cache(self):
        """Configure caching."""
        if self.env.get("NGINX_CACHE_ENABLE"):
            self.update_env("NGINX_CACHE_PATH", f"/var/cache/nginx/{self.app_name}")

    def setup_static(self):
        """Configure static files."""
        # Use BaseProxy's get_static_paths() helper
        static_paths = self.get_static_paths()
        # ... generate location blocks

    def extra_setup(self):
        """Additional Nginx-specific setup."""
        pass

    def generate_config(self):
        """Generate Nginx config file."""
        template = self._load_template("nginx.conf.j2")
        config = template.render(env=self.env, app=self.app)

        config_path = Path(f"/etc/nginx/sites-available/{self.app_name}.conf")
        config_path.write_text(config)

    def check_config(self):
        """Validate Nginx config."""
        subprocess.run(["nginx", "-t"], check=True)

    def reload_proxy(self):
        """Reload Nginx."""
        subprocess.run(["systemctl", "reload", "nginx"], check=True)
```

### 5. OS Setup Strategies

OS setup strategies handle operating system-specific configuration.

**Protocol**: `OS` (from `hop3.core.protocols`)

**Required attributes**:
- `name` (str): OS identifier (e.g., "debian12", "ubuntu2204")
- `display_name` (str): Human-readable name
- `packages` (list[str]): Required system packages

**Required methods**:
- `detect() -> bool`: Check if this OS matches the current system
- `setup_server() -> None`: Install dependencies and configure system
- `ensure_packages(packages, update=True) -> None`: Install system packages
- `ensure_user(user, home, shell, group) -> None`: Create system user

**Example** (simplified Debian family support):

```python
from pathlib import Path
from hop3.core.protocols import OS

class DebianFamilyOS:
    """Support for Debian-based distributions."""

    name = "debian"
    display_name = "Debian Family (Debian, Ubuntu, etc.)"
    packages = [
        "python3", "python3-pip", "python3-venv",
        "nginx", "git", "build-essential"
    ]

    def detect(self) -> bool:
        """Check if this is a Debian-based OS."""
        os_release = Path("/etc/os-release").read_text()
        return "debian" in os_release.lower() or "ubuntu" in os_release.lower()

    def setup_server(self):
        """Setup server for hop3."""
        # Update package lists
        subprocess.run(["apt-get", "update"], check=True)

        # Create hop3 user
        self.ensure_user("hop3", "/home/hop3", "/bin/bash", "hop3")

        # Install required packages
        self.ensure_packages(self.packages)

    def ensure_packages(self, packages, update=True):
        """Install packages with apt."""
        if update:
            subprocess.run(["apt-get", "update"])

        subprocess.run(
            ["apt-get", "install", "-y"] + packages,
            check=True
        )

    def ensure_user(self, user, home, shell, group):
        """Create user if not exists."""
        try:
            subprocess.run(["id", user], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            # User doesn't exist, create it
            subprocess.run([
                "useradd", "-m",
                "-d", home,
                "-s", shell,
                "-U", user  # Create group with same name
            ], check=True)
```

## Registering Plugins

### Internal Plugins (in `hop3.plugins`)

Internal plugins are automatically discovered by scanning the `hop3.plugins` package.

**Plugin structure**:
```
hop3/plugins/
├── my_plugin/
│   ├── __init__.py      # Must import plugin
│   ├── plugin.py        # Plugin class with hooks
│   ├── builder.py       # Strategy implementations
│   └── deployer.py
```

**Plugin class** (`plugin.py`):
```python
from hop3.core.hooks import hookimpl
from .builder import MyBuilder
from .deployer import MyDeployer

class MyPlugin:
    """My custom plugin."""

    name = "my_plugin"

    @hookimpl
    def get_builders(self) -> list:
        """Return build strategies."""
        return [MyBuilder]

    @hookimpl
    def get_deployers(self) -> list:
        """Return deployment strategies."""
        return [MyDeployer]

# Auto-register when module is imported
plugin = MyPlugin()
```

**Important**: The `__init__.py` must import the plugin:
```python
from .plugin import plugin

__all__ = ["plugin"]
```

### External Plugins (via setuptools entry points)

External plugins are distributed as separate Python packages and registered via setuptools entry points.

**Entry point in `setup.py` or `pyproject.toml`**:

```toml
# pyproject.toml
[project.entry-points."hop3.plugins"]
my_plugin = "my_hop3_plugin.plugin:plugin"
```

Or in `setup.py`:
```python
setup(
    name="my-hop3-plugin",
    entry_points={
        "hop3.plugins": [
            "my_plugin = my_hop3_plugin.plugin:plugin"
        ]
    }
)
```

**Package structure**:
```
my-hop3-plugin/
├── pyproject.toml
├── src/
│   └── my_hop3_plugin/
│       ├── __init__.py
│       ├── plugin.py
│       ├── builder.py
│       └── deployer.py
```

**Plugin class**:
```python
# src/my_hop3_plugin/plugin.py
from hop3.core.hooks import hookimpl
from .builder import MyBuilder

class MyExternalPlugin:
    name = "my_external_plugin"

    @hookimpl
    def get_builders(self) -> list:
        return [MyBuilder]

plugin = MyExternalPlugin()
```

## Testing Plugins

### Unit Testing

Test your strategy classes in isolation:

```python
# tests/test_my_builder.py
from pathlib import Path
from hop3.core.protocols import DeploymentContext
from my_hop3_plugin.builder import MyBuilder

def test_accept():
    """Test that builder accepts correct apps."""
    context = DeploymentContext(
        app_name="test",
        source_path=Path("/tmp/test"),
        app_config={}
    )

    builder = MyBuilder(context)
    assert builder.accept() is True

def test_build():
    """Test build process."""
    # ... create test fixtures
    builder = MyBuilder(context)
    artifact = builder.build()

    assert artifact.kind == "my-artifact-type"
    assert Path(artifact.location).exists()
```

### Integration Testing

Test plugin registration and discovery:

```python
# tests/test_plugin_registration.py
from hop3.core.plugins import get_plugin_manager

def test_plugin_registered():
    """Test that plugin is discovered."""
    pm = get_plugin_manager()
    strategies = pm.hook.get_builders()
    strategy_classes = [cls for sublist in strategies for cls in sublist]

    names = [getattr(cls, "name", None) for cls in strategy_classes]
    assert "my_builder" in names
```

### System Testing

Test the full deployment pipeline with your plugin:

```python
# tests/test_deployment.py
def test_deploy_with_my_plugin(tmp_path):
    """Test full deployment using my plugin."""
    # Create test app
    app = App(name="test", runtime="my-runtime")

    # Deploy app
    do_deploy(app)

    # Verify deployment
    assert app.is_running
```

## Best Practices

### 1. Strategy Naming

- Use lowercase names: `"python"`, not `"Python"`
- Be specific: `"docker-compose"` not just `"docker"`
- Avoid conflicts with existing strategies

### 2. Error Handling

- Raise `Abort` from `hop3.lib` for user-facing errors
- Use `log()` from `hop3.lib` for informational messages
- Provide helpful error messages with available options

```python
from hop3.lib import Abort, log

def deploy(self, deltas=None):
    try:
        # ... deployment logic
        log("Deployment successful", fg="green")
    except FileNotFoundError:
        msg = "Docker not found. Please install Docker first."
        raise Abort(msg)
```

### 3. Idempotency

Make operations safe to run multiple times:

```python
def create(self):
    """Create service (idempotent)."""
    if self._already_exists():
        log(f"Service {self.service_name} already exists", fg="yellow")
        return

    # ... create service
```

### 4. Resource Cleanup

Always clean up resources in `destroy()` methods:

```python
def destroy(self):
    """Clean up all service resources."""
    # Stop service
    self.stop()

    # Remove config files
    self._remove_config()

    # Remove data (if appropriate)
    if self.env.get("REMOVE_DATA"):
        self._remove_data()
```

### 5. Configuration

Use environment variables for configuration:

```python
def accept(self) -> bool:
    """Check if builder is enabled."""
    # Allow disabling builder via env var
    if self.context.app_config.get("DISABLE_MY_BUILDER"):
        return False

    return self._detect_app_type()
```

### 6. Documentation

Document your strategies with clear docstrings:

```python
class MyBuilder:
    """Build strategy for MyFramework applications.

    This builder supports MyFramework 2.0+ applications with
    either requirements.txt or Pipfile dependencies.

    Environment Variables:
        MY_BUILDER_VERSION: Specify builder version (default: latest)
        MY_BUILDER_CACHE: Enable build caching (default: true)

    Example hop3.toml:
        [build]
        builder = "my-builder"

        [build.env]
        MY_BUILDER_VERSION = "2.1"
    """
```

## Common Pitfalls

### 1. Forgetting to Register Plugin Instance

**Wrong**:
```python
# plugin.py
class MyPlugin:
    @hookimpl
    def get_builders(self):
        return [MyBuilder]

# Missing: plugin = MyPlugin()
```

**Correct**:
```python
class MyPlugin:
    @hookimpl
    def get_builders(self):
        return [MyBuilder]

# Must create instance for auto-registration
plugin = MyPlugin()
```

### 2. Not Importing Plugin in `__init__.py`

**Wrong**:
```python
# __init__.py
# Empty or missing import
```

**Correct**:
```python
# __init__.py
from .plugin import plugin

__all__ = ["plugin"]
```

### 3. Returning Strategy Instances Instead of Classes

**Wrong**:
```python
@hookimpl
def get_builders(self):
    # Don't instantiate here
    return [MyBuilder()]
```

**Correct**:
```python
@hookimpl
def get_builders(self):
    # Return classes, not instances
    return [MyBuilder]
```

### 4. Hardcoding Paths

**Wrong**:
```python
def build(self):
    venv_path = "/home/hop3/venv"  # Hardcoded
```

**Correct**:
```python
def build(self):
    from hop3.config import HopConfig
    cfg = HopConfig.get_instance()
    venv_path = cfg.APP_ROOT / self.context.app_name / "venv"
```

### 5. Not Checking `check_status()` Properly

**Wrong**:
```python
def check_status(self) -> bool:
    # Just check if config exists (unreliable)
    return Path(f"/etc/systemd/system/{self.app}.service").exists()
```

**Correct**:
```python
def check_status(self) -> bool:
    # Actually verify process is running
    result = subprocess.run(
        ["systemctl", "is-active", f"{self.app}.service"],
        capture_output=True
    )
    return result.returncode == 0
```

## Next Steps

- See [Protocol Reference](protocol-reference.md) for detailed protocol specifications
- See [Hook Specifications](hook-specifications.md) for complete hook documentation
- See [External Plugin Guide](external-plugins.md) for publishing plugins
- Check `hop3/plugins/` for real-world examples

## Getting Help

- Review existing plugins in `hop3/plugins/`
- Check the architectural review: `local-notes/PLUGIN-ARCHITECTURE-REVIEW.md`
- Ask questions in the project discussions
- Read the pluggy documentation: https://pluggy.readthedocs.io/
