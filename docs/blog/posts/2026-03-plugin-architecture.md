---
date: 2026-03-10
template: blog_post.html
description: How we use Pluggy to build a modular, extensible PaaS.
tags:
  - Architecture
  - Plugins
  - Engineering
---

# Hop3's Plugin Architecture: Extensibility Without Complexity

When building a PaaS, you face a fundamental tension: you want to support many languages, databases, and deployment patterns, but you don't want a monolithic codebase that's impossible to maintain. Hop3 solves this with a plugin architecture built on [Pluggy](https://pluggy.readthedocs.io/).

## Why Plugins?

A PaaS needs to handle many concerns:

- **Build**: How do you compile Go? Install Python dependencies? Bundle JavaScript?
- **Deploy**: uWSGI for Python? PM2 for Node? Static files for SPAs?
- **Services**: PostgreSQL? MySQL? Redis? Each with its own setup and credentials
- **Proxy**: Nginx? Caddy? Traefik? Each with different configuration formats
- **OS**: Debian uses `apt`, Fedora uses `dnf`, package names differ

Without plugins, you'd have massive switch statements and tightly coupled code. With plugins, each concern is isolated, testable, and replaceable.

## Plugin Types

Hop3 defines six plugin types, each with a specific responsibility:

### 1. Builders

Builders orchestrate the build process. They decide *where* and *how* to build.

```python
@dataclass(frozen=True)
class LocalBuilder:
    """Build directly on the server."""
    name: str = "local"

    def build(self, app: App, toolchain: LanguageToolchain) -> BuildArtifact:
        return toolchain.build()

@dataclass(frozen=True)
class DockerBuilder:
    """Build inside a Docker container."""
    name: str = "docker"

    def build(self, app: App, toolchain: LanguageToolchain) -> BuildArtifact:
        # Build in isolated container
        ...
```

### 2. Language Toolchains

Toolchains handle language-specific build logic:

```python
class PythonToolchain(LanguageToolchain):
    name = "Python"

    def accept(self) -> bool:
        # Detect Python projects
        return self.check_exists(["requirements.txt", "pyproject.toml"])

    def build(self) -> BuildArtifact:
        self.make_virtual_env()
        self.install_dependencies()
        return self._make_build_artifact(kind="python")
```

Current toolchains: Python, Node.js, Ruby, Go, Rust, PHP, Java, Clojure, Static, Generic.

### 3. Deployers

Deployers run built applications:

```python
@dataclass(frozen=True)
class UWSGIDeployer:
    """Deploy Python/Ruby apps via uWSGI."""
    name: str = "uwsgi"

    def accept(self, artifact: BuildArtifact) -> bool:
        return artifact.kind in ("python", "ruby")

    def deploy(self, app: App, artifact: BuildArtifact) -> None:
        # Generate uWSGI config, start workers
        ...
```

Current deployers: uWSGI, Static, Docker Compose.

### 4. Addons

Addons provision backing services:

```python
@dataclass(frozen=True)
class PostgreSQLAddon:
    name: str = "postgres"

    def create(self, instance_name: str) -> AddonCredential:
        # Create database, user, return credentials
        ...

    def attach(self, app: App, credential: AddonCredential) -> dict[str, str]:
        # Return env vars to inject
        return {"DATABASE_URL": credential.connection_url}
```

Current addons: PostgreSQL, MySQL, Redis.

### 5. Proxy Plugins

Proxy plugins configure reverse proxies:

```python
@dataclass(frozen=True)
class NginxProxy:
    name: str = "nginx"

    def setup(self, app: App, config: ProxyConfig) -> None:
        # Generate nginx server block
        # Handle SSL certificates
        # Reload nginx
        ...
```

Current proxies: Nginx, Caddy, Traefik.

### 6. OS Implementations

OS plugins handle system-level operations:

```python
@dataclass(frozen=True)
class DebianOS:
    name: str = "debian"

    def install_packages(self, packages: list[str]) -> None:
        subprocess.run(["apt-get", "install", "-y", *packages])

    def get_service_manager(self) -> str:
        return "systemd"
```

Current: Debian family (Ubuntu, Debian), Red Hat family (Fedora, Rocky, AlmaLinux), Arch, BSD, macOS.

## Hook Specifications

Plugins register themselves via hook specifications defined in `core/hookspecs.py`:

```python
class Hop3Spec:
    @hookspec
    def get_builders(self) -> list[type[Builder]]:
        """Return available builders."""

    @hookspec
    def get_language_toolchains(self) -> list[type[LanguageToolchain]]:
        """Return available language toolchains."""

    @hookspec
    def get_deployers(self) -> list[type[Deployer]]:
        """Return available deployers."""

    @hookspec
    def get_addons(self) -> list[type[Addon]]:
        """Return available addons."""

    @hookspec
    def get_proxies(self) -> list[type[ProxyPlugin]]:
        """Return available proxy plugins."""

    @hookspec
    def get_os_implementations(self) -> list[type[OSImplementation]]:
        """Return available OS implementations."""
```

## Plugin Discovery

At startup, Hop3 discovers plugins via Pluggy's plugin manager:

```python
pm = pluggy.PluginManager("hop3")
pm.add_hookspecs(Hop3Spec)

# Register built-in plugins
pm.register(BuiltinPlugins())

# Discover external plugins via entry points
pm.load_setuptools_entrypoints("hop3.plugins")
```

External plugins can register via `pyproject.toml`:

```toml
[project.entry-points."hop3.plugins"]
my_plugin = "my_package.hop3_plugin"
```

## Dependency Injection with Dishka

Plugins often need access to shared services (database sessions, configuration, etc.). We use [Dishka](https://github.com/reagento/dishka) for dependency injection:

```python
class RepositoryProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_app_repository(self, session: AsyncSession) -> AppRepository:
        return AppRepository(session=session)

# In a plugin
class MyAddon:
    def create(self, app_repo: AppRepository) -> AddonCredential:
        app = app_repo.get_by_name(self.app_name)
        ...
```

This keeps plugins decoupled from implementation details.

## Writing Your Own Plugin

Here's a minimal example of a custom addon:

```python
# my_addon/plugin.py
from dataclasses import dataclass
from hop3.core.protocols import Addon, AddonCredential

@dataclass(frozen=True)
class MyCustomAddon:
    name: str = "my-service"

    def create(self, instance_name: str) -> AddonCredential:
        # Your provisioning logic here
        return AddonCredential(
            addon_type=self.name,
            instance_name=instance_name,
            credentials={"API_KEY": "..."},
        )

    def destroy(self, credential: AddonCredential) -> None:
        # Cleanup logic
        pass

# Register via hookimpl
import pluggy
hookimpl = pluggy.HookimplMarker("hop3")

class MyPlugin:
    @hookimpl
    def get_addons(self):
        return [MyCustomAddon]
```

## Benefits of This Architecture

1. **Isolation**: Each plugin is self-contained and testable
2. **Extensibility**: Add new languages/services without touching core code
3. **Flexibility**: Swap implementations (Nginx → Caddy) via configuration
4. **Maintainability**: Clear boundaries between concerns
5. **Community**: External plugins without forking

## Learn More

- [Plugin Development Guide](/developers/plugin-development/)
- [ADR 020: Pluggable Architecture](/adrs/020-pluggable-architecture/)
- [ADR 028: Pluggy-Dishka Integration](/adrs/028-pluggy-dishka-integration/)

---

*Related posts: [Package Architecture](2026-03-package-architecture.md) explains how we split Hop3 into focused packages. [The BuildArtifact Pattern](2026-03-build-artifact-pattern.md) shows how plugins produce portable build artifacts. For plugin development, see the [Plugin Development Guide](/developers/plugin-development/).*
