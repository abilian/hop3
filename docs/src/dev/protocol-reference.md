# Protocol Reference

This document provides comprehensive reference documentation for all protocols (interfaces) in the Hop3 plugin system.

All protocols are defined in `hop3/core/protocols.py` using Python's PEP 544 Protocol typing.

## Table of Contents

- [Data Structures](#data-structures)
  - [DeploymentContext](#deploymentcontext)
  - [BuildArtifact](#buildartifact)
  - [DeploymentInfo](#deploymentinfo)
- [Strategy Protocols](#strategy-protocols)
  - [BuildStrategy](#buildstrategy)
  - [Deployer](#Deployer)
  - [ServiceStrategy](#servicestrategy)
  - [Proxy](#proxy)
  - [BaseProxy](#baseproxy)
  - [OS](#OS)

---

## Data Structures

### DeploymentContext

**Location**: `hop3.core.protocols.DeploymentContext`

**Purpose**: Carries contextual information about an application deployment.

**Attributes**:

| Attribute | Type | Description |
|-----------|------|-------------|
| `app_name` | `str` | Name of the application being deployed |
| `source_path` | `Path` | Path to application source code |
| `app_config` | `dict` | Application configuration from hop3.toml |
| `app` | `App \| None` | Optional full App database object |

**Usage**:
```python
from pathlib import Path
from hop3.core.protocols import DeploymentContext

context = DeploymentContext(
    app_name="myapp",
    source_path=Path("/home/hop3/apps/myapp/src"),
    app_config={"workers": {"web": "gunicorn app:app"}},
    app=app_instance  # Optional
)
```

**Validation**: The `source_path` must be a directory (validated in `__post_init__`).

---

### BuildArtifact

**Location**: `hop3.core.protocols.BuildArtifact`

**Purpose**: Represents the output of a build process.

**Attributes**:

| Attribute | Type | Description |
|-----------|------|-------------|
| `kind` | `str` | Type of artifact: "virtualenv", "docker-image", "buildpack", etc. |
| `location` | `str` | Path or reference to the artifact (e.g., "/path/to/venv", "image:tag") |
| `metadata` | `dict[str, Any]` | Additional information about the artifact (versions, sizes, etc.) |

**Usage**:
```python
from hop3.core.protocols import BuildArtifact

# Virtualenv artifact
artifact = BuildArtifact(
    kind="virtualenv",
    location="/home/hop3/apps/myapp/venv",
    metadata={"python_version": "3.11.2"}
)

# Docker image artifact
artifact = BuildArtifact(
    kind="docker-image",
    location="myapp:v1.2.3",
    metadata={"image_id": "sha256:abc123", "size_mb": 145}
)
```

---

### DeploymentInfo

**Location**: `hop3.core.protocols.DeploymentInfo`

**Purpose**: Information returned by a deployment strategy about where the app is running.

**Attributes**:

| Attribute | Type | Description |
|-----------|------|-------------|
| `protocol` | `str` | Protocol used: "http", "https", "tcp", "unix" |
| `address` | `str` | IP address or hostname where app is accessible |
| `port` | `int \| None` | Port number (None for Unix sockets) |

**Usage**:
```python
from hop3.core.protocols import DeploymentInfo

# HTTP deployment
info = DeploymentInfo(
    protocol="http",
    address="127.0.0.1",
    port=8080
)

# Unix socket deployment
info = DeploymentInfo(
    protocol="unix",
    address="/tmp/myapp.sock",
    port=None
)
```

---

## Strategy Protocols

### BuildStrategy

**Location**: `hop3.core.protocols.BuildStrategy`

**Purpose**: Convert source code into a runnable artifact.

**Required Attributes**:

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Unique identifier (e.g., "python", "docker", "node") |
| `context` | `DeploymentContext` | Deployment context with app information |

**Required Methods**:

#### `accept() -> bool`

Determine if this strategy can build the application.

**Returns**: `True` if the strategy can build this app, `False` otherwise.

**Implementation Guidelines**:
- Check for framework-specific files (requirements.txt, package.json, etc.)
- Check configuration settings
- Verify required tools are available
- Should be fast (no expensive operations)

**Example**:
```python
def accept(self) -> bool:
    """Accept if requirements.txt or pyproject.toml exists."""
    src_path = self.context.source_path
    return (src_path / "requirements.txt").exists() or \
           (src_path / "pyproject.toml").exists()
```

#### `build() -> BuildArtifact`

Execute the build process and return artifact information.

**Returns**: `BuildArtifact` describing what was built.

**Raises**:
- `Abort` (from `hop3.lib`) for user-facing errors
- Other exceptions for unexpected errors

**Implementation Guidelines**:
- Create isolated build environment (virtualenv, container, etc.)
- Install dependencies
- Compile code if needed
- Verify build succeeded
- Return artifact details

**Example**:
```python
def build(self) -> BuildArtifact:
    """Build Python virtualenv."""
    venv_path = self._create_virtualenv()
    self._install_dependencies(venv_path)

    return BuildArtifact(
        kind="virtualenv",
        location=str(venv_path),
        metadata={"python_version": self._get_python_version()}
    )
```

**Complete Example**:

See `packages/hop3-server/src/hop3/builders/python.py` for the canonical Python builder implementation.

---

### Deployer

**Location**: `hop3.core.protocols.Deployer`

**Purpose**: Run a build artifact and manage its lifecycle.

**Required Attributes**:

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Unique identifier (e.g., "uwsgi", "docker-compose", "systemd") |
| `context` | `DeploymentContext` | Deployment context |
| `artifact` | `BuildArtifact` | Build artifact to deploy |

**Required Methods**:

#### `accept() -> bool`

Determine if this strategy can deploy the given artifact.

**Returns**: `True` if the strategy can deploy this artifact type.

**Example**:
```python
def accept(self) -> bool:
    """Accept docker-image artifacts."""
    return self.artifact.kind == "docker-image"
```

#### `deploy(deltas: dict[str, int] | None = None) -> DeploymentInfo`

Deploy the artifact.

**Parameters**:
- `deltas`: Optional dictionary of worker scaling changes (`{"web": 2, "worker": 1}`)

**Returns**: `DeploymentInfo` with connection details for the proxy.

**Implementation Guidelines**:
- Start application processes/containers
- Configure workers based on deltas
- Wait for startup (or return immediately if async)
- Return connection information

**Example**:
```python
def deploy(self, deltas=None) -> DeploymentInfo:
    """Deploy with uWSGI."""
    self._write_uwsgi_config()
    self._symlink_to_emperor()  # uWSGI emperor auto-starts

    return DeploymentInfo(
        protocol="http",
        address="127.0.0.1",
        port=self.context.app.port
    )
```

#### `stop() -> None`

Stop the running application.

**Implementation Guidelines**:
- Gracefully shut down processes/containers
- Clean up runtime resources (sockets, PID files)
- Should be idempotent (safe to call multiple times)

**Example**:
```python
def stop(self) -> None:
    """Stop by removing emperor symlink."""
    config_file = Path(f"/etc/uwsgi/enabled/{self.context.app_name}.ini")
    if config_file.exists():
        config_file.unlink()
```

#### `check_status() -> bool`

Check if the application is actually running.

**Returns**: `True` if processes/containers are confirmed running, `False` otherwise.

**Implementation Guidelines**:
- Verify actual running state (don't just check config files)
- For uWSGI: check socket files, process listings, config files
- For Docker: check container status (`docker ps`)
- For systemd: check service status (`systemctl is-active`)
- Should be reliable and fast
- Should not raise exceptions (return `False` on errors)

**Example**:
```python
def check_status(self) -> bool:
    """Check if Docker containers are running."""
    result = subprocess.run(
        ["docker", "compose", "ps", "--format", "{{.State}}"],
        cwd=self.context.source_path,
        capture_output=True,
        text=True,
        timeout=5
    )

    if result.returncode != 0:
        return False

    return "running" in result.stdout.lower()
```

#### `scale(deltas: dict[str, int] | None = None) -> None`

Scale workers up or down.

**Parameters**:
- `deltas`: Dictionary mapping worker names to scaling changes (e.g., `{"web": 2}` to set 2 web workers)

**Implementation Guidelines**:
- Adjust number of worker processes/containers
- May trigger restart/reload
- Should be graceful (no downtime if possible)

**Example**:
```python
def scale(self, deltas=None):
    """Scale Docker Compose services."""
    if not deltas:
        return

    scale_args = []
    for service, count in deltas.items():
        scale_args.extend(["--scale", f"{service}={count}"])

    cmd = ["docker", "compose", "up", "-d"] + scale_args
    subprocess.run(cmd, cwd=self.context.source_path, check=True)
```

**Optional Methods**:

These methods may be provided for additional functionality:

- `start() -> None`: Start a stopped application
- `restart() -> None`: Restart a running application
- `get_status() -> dict`: Get detailed status information

**Complete Example**:

See `packages/hop3-server/src/hop3/plugins/docker/deployer.py` for the Docker Compose implementation.

---

### ServiceStrategy

**Location**: `hop3.core.protocols.ServiceStrategy`

**Purpose**: Manage backing services (databases, caches, message queues, etc.).

**Required Attributes**:

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Service type (e.g., "postgres", "redis", "mysql") |
| `service_name` | `str` | Specific instance name for this service |

**Required Methods**:

#### `create() -> None`

Create a new service instance.

**Implementation Guidelines**:
- Provision necessary resources (database, user, directories)
- Configure service
- Start service
- Should be idempotent

**Example**:
```python
def create(self) -> None:
    """Create PostgreSQL database."""
    # Check if already exists
    if self._database_exists():
        log(f"Database {self.service_name} already exists", fg="yellow")
        return

    # Create database and user
    subprocess.run([
        "sudo", "-u", "postgres", "createdb", self.service_name
    ], check=True)
```

#### `destroy() -> None`

Destroy the service instance and all its data.

**Implementation Guidelines**:
- Stop service
- Remove all data (WARNING: destructive)
- Remove configuration
- Should be idempotent

**Example**:
```python
def destroy(self) -> None:
    """Destroy PostgreSQL database."""
    subprocess.run([
        "sudo", "-u", "postgres", "dropdb", "--if-exists", self.service_name
    ])
```

#### `get_connection_details() -> dict[str, str]`

Get environment variables for applications to connect to this service.

**Returns**: Dictionary mapping environment variable names to values.

**Implementation Guidelines**:
- Return standard connection URLs (DATABASE_URL, REDIS_URL, etc.)
- Include all necessary connection parameters
- Use localhost for local services

**Example**:
```python
def get_connection_details(self) -> dict[str, str]:
    """Return PostgreSQL connection details."""
    return {
        "DATABASE_URL": f"postgresql://hop3:password@localhost/{self.service_name}",
        "POSTGRES_DB": self.service_name,
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432"
    }
```

#### `backup() -> Path`

Create a backup of service data.

**Returns**: Path to the backup file or directory.

**Implementation Guidelines**:
- Create complete backup of data
- Use service-specific backup tools (pg_dump, redis-cli SAVE, etc.)
- Include timestamps in filename
- Store in predictable location

**Example**:
```python
def backup(self) -> Path:
    """Backup PostgreSQL database."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = Path(f"/home/hop3/backups/postgres_{self.service_name}_{timestamp}.sql")

    with backup_file.open("w") as f:
        subprocess.run([
            "sudo", "-u", "postgres", "pg_dump", self.service_name
        ], stdout=f, check=True)

    return backup_file
```

#### `restore(backup_path: Path) -> None`

Restore service data from a backup.

**Parameters**:
- `backup_path`: Path to backup file/directory to restore from

**Implementation Guidelines**:
- Stop service if necessary
- Clear existing data (optional, based on strategy)
- Restore from backup
- Restart service

**Example**:
```python
def restore(self, backup_path: Path) -> None:
    """Restore PostgreSQL database."""
    # Drop and recreate database
    self.destroy()
    self.create()

    # Restore from backup
    with backup_path.open() as f:
        subprocess.run([
            "sudo", "-u", "postgres", "psql", self.service_name
        ], stdin=f, check=True)
```

#### `info() -> dict[str, Any]`

Get information about the service instance.

**Returns**: Dictionary with service details.

**Implementation Guidelines**:
- Include status, version, size, etc.
- Don't include sensitive data (passwords)
- Should be fast

**Example**:
```python
def info(self) -> dict[str, Any]:
    """Get PostgreSQL database info."""
    # Get database size
    result = subprocess.run([
        "sudo", "-u", "postgres", "psql", "-c",
        f"SELECT pg_database_size('{self.service_name}');"
    ], capture_output=True, text=True)

    return {
        "service_type": "postgres",
        "service_name": self.service_name,
        "status": "running" if self._is_running() else "stopped",
        "version": self._get_version(),
        "size_bytes": self._parse_size(result.stdout)
    }
```

**Complete Example**:

See `packages/hop3-server/src/hop3/plugins/postgresql/service.py` for the PostgreSQL service implementation.

---

### Proxy

**Location**: `hop3.core.protocols.Proxy`

**Purpose**: Basic protocol interface for reverse proxies (legacy).

**Note**: Most proxy implementations should use `BaseProxy` instead, which provides common functionality.

**Required Attributes**:

| Attribute | Type | Description |
|-----------|------|-------------|
| `app` | `App` | Application database object |
| `env` | `Env` | Environment variables |
| `workers` | `dict[str, str]` | Worker configuration from Procfile |

**Required Methods**:

#### `setup() -> None`

Configure the proxy for this application.

---

### BaseProxy

**Location**: `hop3.core.protocols.BaseProxy`

**Purpose**: Abstract base class for proxy implementations (Nginx, Caddy, Traefik, etc.).

**Inheritance**: Concrete proxy classes should inherit from `BaseProxy` and implement the abstract methods.

**Attributes** (provided by base class):

| Attribute | Type | Description |
|-----------|------|-------------|
| `app` | `App` | Application database object |
| `env` | `Env` | Environment variables |
| `workers` | `dict[str, str]` | Worker configuration |

**Properties** (provided by base class):

| Property | Type | Description |
|----------|------|-------------|
| `app_name` | `str` | Application name (from `app.name`) |
| `app_path` | `Path` | Application directory (from `app.app_path`) |
| `src_path` | `Path` | Source directory (from `app.src_path`) |

**Abstract Methods** (must be implemented):

#### `get_proxy_name() -> str`

Return the proxy name for environment variable prefixes.

**Returns**: One of "nginx", "caddy", "traefik", etc.

**Example**:
```python
def get_proxy_name(self) -> str:
    return "nginx"
```

#### `setup_backend() -> None`

Configure the backend connection (TCP port or Unix socket).

**Implementation Guidelines**:
- Set `NGINX_SOCKET` or `NGINX_BACKEND` environment variables
- Choose between Unix socket and TCP based on configuration

**Example**:
```python
def setup_backend(self) -> None:
    """Configure Nginx backend."""
    if self.env.get("NGINX_SOCKET"):
        socket_path = f"/tmp/{self.app_name}.sock"
        self.update_env("NGINX_SOCKET", socket_path)
    else:
        port = self.app.port
        self.update_env("NGINX_BACKEND", f"127.0.0.1:{port}")
```

#### `setup_certificates() -> None`

Setup SSL/TLS certificates for the application.

**Implementation Guidelines**:
- Generate self-signed certificates for development
- Integrate with Let's Encrypt for production
- Set certificate paths in environment

#### `setup_cache() -> None`

Configure caching for the application.

**Implementation Guidelines**:
- Enable/disable based on environment variables
- Configure cache paths
- Set cache parameters (size, TTL, etc.)

#### `setup_static() -> None`

Configure static file serving.

**Implementation Guidelines**:
- Use `self.get_static_paths()` helper method
- Generate location/route blocks for each static path
- Configure caching headers

#### `extra_setup() -> None`

Perform additional proxy-specific setup.

**Implementation Guidelines**:
- Custom headers
- Redirect rules
- Rate limiting
- Access controls

#### `generate_config() -> None`

Generate the proxy configuration file.

**Implementation Guidelines**:
- Use templates (Jinja2 recommended)
- Render with `self.env` and `self.app` context
- Write to proxy-specific config directory

#### `check_config() -> None`

Validate the generated configuration.

**Implementation Guidelines**:
- Use proxy's config test command (`nginx -t`, etc.)
- Raise exception if validation fails

#### `reload_proxy() -> None`

Reload the proxy to apply configuration changes.

**Implementation Guidelines**:
- Try supervisor control first
- Fall back to systemctl
- Fall back to direct command (`nginx -s reload`)
- Should be graceful (no downtime)

**Provided Methods** (from base class):

#### `update_env(key: str, value: str = "", template: str = "") -> None`

Update an environment variable, optionally from a template.

**Parameters**:
- `key`: Environment variable name
- `value`: Value to set (if template is empty)
- `template`: Template string to format with current env vars

**Example**:
```python
# Set directly
self.update_env("NGINX_BACKEND", "127.0.0.1:8080")

# Use template
self.update_env("CACHE_PATH", template="/var/cache/{app_name}")
```

#### `setup() -> None`

Main setup orchestrator (already implemented, don't override).

This method calls all setup methods in the correct order:
1. `setup_backend()`
2. `setup_certificates()`
3. `setup_cache()`
4. `setup_static()`
5. `extra_setup()`
6. `generate_config()`
7. `check_config()`
8. `reload_proxy()`

#### `get_static_paths() -> list[tuple[str, Path]]`

Get static URL-to-filesystem mappings.

**Returns**: List of tuples `(url_prefix, filesystem_path)`.

**Implementation**: Reads from `{PROXY_NAME}_STATIC_PATHS` environment variable.

**Format**: `/url:filesystem/path,/url2:path2`

**Example**:
```python
# If NGINX_STATIC_PATHS="/static:static/,/media:media/"
static_paths = self.get_static_paths()
# Returns: [("/static", Path(".../static")), ("/media", Path(".../media"))]
```

**Complete Example**:

See `packages/hop3-server/src/hop3/plugins/proxy/nginx/_setup.py` for the Nginx implementation.

---

### OS

**Location**: `hop3.core.protocols.OS`

**Purpose**: Handle operating system-specific server setup and package management.

**Required Attributes**:

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | OS identifier (e.g., "debian12", "ubuntu2204") |
| `display_name` | `str` | Human-readable name (e.g., "Debian 12 (Bookworm)") |
| `packages` | `list[str]` | Required system packages for hop3 |

**Required Methods**:

#### `detect() -> bool`

Check if this strategy matches the current operating system.

**Returns**: `True` if this OS strategy should be used on the current system.

**Implementation Guidelines**:
- Read `/etc/os-release` or similar files
- Check distribution name and version
- Return `True` only for exact matches or families

**Example**:
```python
def detect(self) -> bool:
    """Check if this is Debian 12."""
    if not Path("/etc/os-release").exists():
        return False

    os_release = Path("/etc/os-release").read_text()
    return "debian" in os_release.lower() and "12" in os_release
```

#### `setup_server() -> None`

Install dependencies and configure the system for hop3.

**Implementation Guidelines**:
1. Configure package manager settings
2. Create hop3 user account
3. Install required system packages
4. Set up directories and permissions
5. Should be idempotent

**Example**:
```python
def setup_server(self) -> None:
    """Setup Debian server."""
    # Update package lists
    subprocess.run(["apt-get", "update"], check=True)

    # Create hop3 user
    self.ensure_user("hop3", "/home/hop3", "/bin/bash", "hop3")

    # Install packages
    self.ensure_packages(self.packages)

    # Additional setup
    self._configure_firewall()
```

#### `ensure_packages(packages: list[str], *, update: bool = True) -> None`

Install system packages using the OS package manager.

**Parameters**:
- `packages`: List of package names to install
- `update`: Whether to update package lists first (default: True)

**Implementation Guidelines**:
- Use OS-specific package manager (apt, yum, dnf, pacman, etc.)
- Should be idempotent (don't reinstall if already installed)
- Handle errors gracefully

**Example**:
```python
def ensure_packages(self, packages, *, update=True):
    """Install packages with apt."""
    if update:
        subprocess.run(["apt-get", "update"])

    subprocess.run(
        ["apt-get", "install", "-y", "--no-install-recommends"] + packages,
        check=True
    )
```

#### `ensure_user(user: str, home: str, shell: str, group: str) -> None`

Create a system user account if it doesn't exist.

**Parameters**:
- `user`: Username to create
- `home`: Home directory path
- `shell`: Default shell path
- `group`: Primary group name

**Implementation Guidelines**:
- Check if user already exists
- Create user with specified settings
- Should be idempotent

**Example**:
```python
def ensure_user(self, user, home, shell, group):
    """Create user if not exists."""
    try:
        subprocess.run(["id", user], check=True, capture_output=True)
        # User exists, nothing to do
    except subprocess.CalledProcessError:
        # User doesn't exist, create it
        subprocess.run([
            "useradd",
            "-m",            # Create home directory
            "-d", home,      # Home directory path
            "-s", shell,     # Login shell
            "-U",            # Create group with same name
            user
        ], check=True)
```

**Complete Example**:

See `packages/hop3-server/src/hop3/plugins/oses/debian_family.py` for the Debian/Ubuntu implementation.

---

## Protocol Compliance Checklist

When implementing a strategy, use this checklist to ensure protocol compliance:

### BuildStrategy
- [ ] `name` attribute set to unique string
- [ ] `context` attribute assigned in `__init__`
- [ ] `accept()` method returns bool
- [ ] `accept()` is fast (no expensive operations)
- [ ] `build()` returns `BuildArtifact`
- [ ] `build()` raises `Abort` for user-facing errors
- [ ] Build creates isolated environment
- [ ] Build is reproducible

### Deployer
- [ ] `name` attribute set to unique string
- [ ] `context` and `artifact` attributes assigned
- [ ] `accept()` checks `artifact.kind`
- [ ] `deploy()` returns `DeploymentInfo`
- [ ] `deploy()` handles optional `deltas` parameter
- [ ] `stop()` is idempotent
- [ ] `check_status()` verifies actual running state
- [ ] `check_status()` doesn't raise exceptions
- [ ] `scale()` handles worker scaling

### ServiceStrategy
- [ ] `name` attribute set (service type)
- [ ] `service_name` attribute set (instance name)
- [ ] `create()` is idempotent
- [ ] `destroy()` removes all data
- [ ] `get_connection_details()` returns connection URLs
- [ ] `backup()` returns Path to backup file
- [ ] `restore()` accepts Path parameter
- [ ] `info()` returns status dictionary

### BaseProxy
- [ ] Inherits from `BaseProxy`
- [ ] Uses `@dataclass(frozen=True)` decorator
- [ ] `get_proxy_name()` returns lowercase name
- [ ] All abstract methods implemented
- [ ] `setup()` not overridden (use template method)
- [ ] `reload_proxy()` is graceful
- [ ] Uses `get_static_paths()` helper

### OS
- [ ] `name` attribute set (OS identifier)
- [ ] `display_name` attribute set
- [ ] `packages` list defined
- [ ] `detect()` checks `/etc/os-release`
- [ ] `setup_server()` is idempotent
- [ ] `ensure_packages()` handles update parameter
- [ ] `ensure_user()` is idempotent

---

## See Also

- [Plugin Development Guide](plugin-development.md) - How to create plugins
- [Hook Specifications](hook-specifications.md) - How to register strategies
- [External Plugin Guide](external-plugins.md) - Publishing external plugins
