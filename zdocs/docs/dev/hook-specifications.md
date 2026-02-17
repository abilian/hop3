# Hook Specifications

This document provides comprehensive documentation for the Hop3 plugin hook system, built on [pluggy](https://pluggy.readthedocs.io/).

## Overview

Hop3 uses pluggy's hook system to allow plugins to register strategies and extend functionality. Hooks are defined in `hop3/core/hookspecs.py` and implemented by plugins using the `@hookimpl` decorator.

## Hook System Architecture

### Hook Definitions

Hooks are defined using the `@hookspec` decorator in `hookspecs.py`:

```python
from hop3.core.hooks import hookspec

@hookspec
def get_builders() -> list:
    """Get build strategies provided by this plugin."""
```

### Hook Implementations

Plugins implement hooks using the `@hookimpl` decorator:

```python
from hop3.core.hooks import hookimpl

class MyPlugin:
    @hookimpl
    def get_builders(self) -> list:
        return [MyBuildStrategy]
```

### Hook Calling

Hooks are called via the plugin manager:

```python
from hop3.core.plugins import get_plugin_manager

pm = get_plugin_manager()
results = pm.hook.get_builders()  # Returns list of lists
# Flatten results
builders = [item for sublist in results for item in sublist]
```

## Available Hooks

### get_builders

**Purpose**: Register builders for converting source code to artifacts.

**Location**: `hop3.core.hookspecs.get_builders`

**Signature**:
```python
@hookspec
def get_builders() -> list:
    """Get build strategies provided by this plugin.

    Returns:
        List of Builder classes
    """
```

**Returns**: List of classes implementing `Builder` protocol.

**Implementation Example**:

```python
from hop3.core.hooks import hookimpl
from .python_builder import PythonBuilder
from .docker_builder import DockerBuilder

class MyPlugin:
    @hookimpl
    def get_builders(self) -> list:
        """Provide Python and Docker build strategies."""
        return [PythonBuilder, DockerBuilder]
```

**Usage in Core**:

The build pipeline uses this hook to discover available builders:

```python
from hop3.core.plugins import get_build_strategy

# Automatically finds accepting strategy from all registered builders
strategy = get_build_strategy(context, artifact)
```

**Notes**:
- Return strategy **classes**, not instances
- Each class must have a `name` attribute
- Each class must implement the `Builder` protocol
- Multiple plugins can provide build strategies
- Strategies are tried in registration order until one accepts

---

### get_deployers

**Purpose**: Register deployment strategies (runtimes) for running artifacts.

**Location**: `hop3.core.hookspecs.get_deployers`

**Signature**:
```python
@hookspec
def get_deployers() -> list:
    """Get deployment strategies provided by this plugin.

    Returns:
        List of Deployer classes
    """
```

**Returns**: List of classes implementing `Deployer` protocol.

**Implementation Example**:

```python
from hop3.core.hooks import hookimpl
from .uwsgi_deployer import UWSGIDeployer
from .systemd_deployer import SystemdDeployer

class MyPlugin:
    @hookimpl
    def get_deployers(self) -> list:
        """Provide uWSGI and systemd deployment strategies."""
        return [UWSGIDeployer, SystemdDeployer]
```

**Usage in Core**:

Deployment strategies are used in two ways:

1. **During deployment** (auto-selection):
```python
from hop3.core.plugins import get_deployment_strategy

# Finds strategy that accepts the artifact
strategy = get_deployment_strategy(context, artifact)
```

2. **For lifecycle operations** (by name):
```python
from hop3.core.plugins import get_deployer_by_name

# Look up strategy by name for start/stop/restart
strategy = get_deployer_by_name(app, "docker-compose")
```

**Notes**:
- Return strategy **classes**, not instances
- Each class must have a `name` attribute
- Each class must implement the `Deployer` protocol
- The `name` attribute is used to match `app.runtime` field
- Multiple strategies can exist; selection is by `accept()` or by name

---

### get_addons

**Purpose**: Register service strategies for managing backing services.

**Location**: `hop3.core.hookspecs.get_addons`

**Signature**:
```python
@hookspec
def get_addons() -> list:
    """Get service strategies provided by this plugin.

    Returns:
        List of Addon classes
    """
```

**Returns**: List of classes implementing `Addon` protocol.

**Implementation Example**:

```python
from hop3.core.hooks import hookimpl
from .postgres_service import PostgresService
from .redis_service import RedisService

class DatabasePlugin:
    @hookimpl
    def get_addons(self) -> list:
        """Provide PostgreSQL and Redis service strategies."""
        return [PostgresService, RedisService]
```

**Usage in Core**:

Services are managed through the CLI and API:

```python
from hop3.core.plugins import get_addon

# Find service strategy by name
strategy_class = get_addon("postgres")

# Instantiate for specific service instance
service = strategy_class(service_name="mydb")

# Use service
service.create()
connection = service.get_connection_details()
```

**Notes**:
- Return strategy **classes**, not instances
- Each class must have a `name` attribute (service type)
- Each class must implement the `Addon` protocol
- Service instances are created per database/cache/etc.
- Multiple plugins can provide different service types

---

### get_os_implementations

**Purpose**: Register OS setup strategies for different Linux distributions.

**Location**: `hop3.core.hookspecs.get_os_implementations`

**Signature**:
```python
@hookspec
def get_os_implementations() -> list:
    """Get OS setup strategies provided by this plugin.

    Returns:
        List of OS classes that can detect and configure
        specific operating systems for hop3.
    """
```

**Returns**: List of classes implementing `OS` protocol.

**Implementation Example**:

```python
from hop3.core.hooks import hookimpl
from .debian import DebianOS
from .ubuntu import UbuntuOS

class DebianPlugin:
    @hookimpl
    def get_os_implementations(self) -> list:
        """Provide Debian and Ubuntu OS strategies."""
        return [DebianOS, UbuntuOS]
```

**Usage in Core**:

OS strategies are used during server setup:

```python
from hop3.core.plugins import detect_os

# Auto-detect current OS
os_strategy = detect_os()  # Calls detect() on each strategy

# Setup server
os_strategy.setup_server()
```

**Notes**:
- Return strategy **classes**, not instances
- Each class must have `name` and `display_name` attributes
- Each class must implement `detect()` to identify if it matches the current OS
- Only one strategy should detect `True` per system
- Used primarily by the installer and setup commands

---

### get_proxies

**Purpose**: Register reverse proxy strategies (Nginx, Caddy, Traefik, etc.).

**Location**: `hop3.core.hookspecs.get_proxies`

**Signature**:
```python
@hookspec
def get_proxies() -> list:
    """Get proxy strategies provided by this plugin.

    Returns:
        List of Proxy classes that can configure reverse proxies
        (Nginx, Caddy, Traefik, etc.) for hop3 applications.
    """
```

**Returns**: List of classes implementing `Proxy` or inheriting from `BaseProxy`.

**Implementation Example**:

```python
from hop3.core.hooks import hookimpl
from .nginx_proxy import NginxVirtualHost
from .caddy_proxy import CaddyVirtualHost

class ProxyPlugin:
    @hookimpl
    def get_proxies(self) -> list:
        """Provide Nginx and Caddy proxy strategies."""
        return [NginxVirtualHost, CaddyVirtualHost]
```

**Usage in Core**:

Proxies are selected based on configuration:

```python
from hop3.config import HopConfig

cfg = HopConfig.get_instance()
proxy_type = cfg.PROXY_TYPE  # "nginx", "caddy", etc.

# Find matching proxy strategy
proxy_class = get_proxy_strategy(proxy_type)

# Instantiate and configure
proxy = proxy_class(app=app, env=env, workers=workers)
proxy.setup()
```

**Notes**:
- Return proxy **classes**, not instances
- Should inherit from `BaseProxy` for code reuse
- Each proxy type should have a unique name
- Only one proxy type is active per hop3 installation
- Configuration is in `HopConfig.PROXY_TYPE`

---

### get_di_providers

**Purpose**: Register dependency injection providers for the application container.

**Location**: `hop3.core.hookspecs.get_di_providers`

**Signature**:
```python
@hookspec
def get_di_providers() -> list:
    """Get DI providers from this plugin.

    Plugins can implement this hook to contribute Dishka providers
    to the application's dependency injection container.

    Returns:
        List of Dishka Provider instances that will be registered
        in the application container.

    Example:
        ```python
        from dishka import Provider, provide, Scope

        class MyPluginProvider(Provider):
            scope = Scope.APP

            @provide
            def get_my_service(self) -> MyService:
                return MyService()

        @hop3_hook_impl
        def get_di_providers() -> list:
            return [MyPluginProvider()]
        ```
    """
```

**Returns**: List of Dishka `Provider` **instances** (not classes).

**Implementation Example**:

```python
from dishka import Provider, provide, Scope
from hop3.core.hooks import hookimpl
from .postgres_service import PostgresService

class PostgresProvider(Provider):
    """DI provider for PostgreSQL service."""

    scope = Scope.APP

    @provide
    def get_postgres_service(self) -> PostgresService:
        """Provide PostgresService singleton."""
        return PostgresService()

class PostgresPlugin:
    @hookimpl
    def get_di_providers(self) -> list:
        """Register PostgreSQL service in DI container."""
        return [PostgresProvider()]
```

**Usage in Core**:

DI providers are collected during application startup:

```python
from hop3.core.plugins import get_plugin_manager

pm = get_plugin_manager()
provider_lists = pm.hook.get_di_providers()
providers = [p for sublist in provider_lists for p in sublist]

# Add to Dishka container
for provider in providers:
    container.add_provider(provider)
```

**Notes**:
- Return provider **instances**, not classes (unlike other hooks)
- Use Dishka's `Provider` class
- Define scope appropriately (`Scope.APP`, `Scope.REQUEST`, etc.)
- Services are available for dependency injection in controllers, etc.
- See [Dishka documentation](https://dishka.readthedocs.io/) for details

---

### cli_commands

**Purpose**: Register custom CLI commands.

**Location**: `hop3.core.hookspecs.cli_commands`

**Signature**:
```python
@hookspec
def cli_commands() -> None:
    """Get CLI commands."""
```

**Returns**: None (commands are registered via Click decorators).

**Implementation Example**:

```python
import click
from hop3.core.hooks import hookimpl

@click.command()
@click.argument("service_name")
def create_postgres(service_name):
    """Create a PostgreSQL database."""
    # ... implementation
    click.echo(f"Created PostgreSQL service: {service_name}")

class PostgresPlugin:
    @hookimpl
    def cli_commands(self) -> None:
        """Register postgres CLI command."""
        # Register with Click CLI
        from hop3.cli import cli
        cli.add_command(create_postgres, name="postgres:create")
```

**Usage in Core**:

CLI commands are loaded during CLI initialization:

```python
from hop3.core.plugins import get_plugin_manager

pm = get_plugin_manager()
pm.hook.cli_commands()  # Triggers all implementations
```

**Notes**:
- Use Click for command definitions
- Commands should follow naming convention: `service:action`
- Commands are added to the main `hop` CLI
- Return `None` (registration is side-effect based)

---

## Hook Call Order

Pluggy calls hooks in **last-registered-first-executed (LIFO)** order by default. For Hop3:

1. **Internal plugins** (in `hop3.plugins`) are registered first (in package scan order)
2. **External plugins** (from entry points) are registered after

This means external plugins can override internal behavior if needed.

### Controlling Hook Order

To ensure a hook runs first or last, use `hookimpl` options:

```python
@hookimpl(tryfirst=True)
def get_builders(self) -> list:
    """This will be called before other implementations."""
    return [MyBuilder]

@hookimpl(trylast=True)
def get_builders(self) -> list:
    """This will be called after other implementations."""
    return [FallbackBuilder]
```

---

## Return Value Conventions

### Lists of Classes

Most hooks return lists of **strategy classes** (not instances):

```python
# Correct
@hookimpl
def get_builders(self) -> list:
    return [PythonBuilder, NodeBuilder]

# Wrong - don't instantiate
@hookimpl
def get_builders(self) -> list:
    return [PythonBuilder(), NodeBuilder()]  # ❌
```

**Why**: The core code needs to instantiate strategies with specific contexts, artifacts, etc. that aren't available during hook registration.

### Exception: DI Providers

The `get_di_providers()` hook is the exception - it returns **provider instances**:

```python
@hookimpl
def get_di_providers(self) -> list:
    return [MyProvider()]  # ✅ Instances, not classes
```

---

## Hook Implementation Patterns

### Simple Plugin

Implements one hook, provides one strategy:

```python
from hop3.core.hooks import hookimpl
from .redis_service import RedisService

class RedisPlugin:
    name = "redis"

    @hookimpl
    def get_addons(self) -> list:
        return [RedisService]

# Auto-register
plugin = RedisPlugin()
```

### Multi-Strategy Plugin

Implements one hook, provides multiple strategies:

```python
from hop3.core.hooks import hookimpl
from .python_builder import PythonBuilder
from .node_builder import NodeBuilder
from .ruby_builder import RubyBuilder

class BuildpackPlugin:
    name = "buildpack"

    @hookimpl
    def get_builders(self) -> list:
        return [PythonBuilder, NodeBuilder, RubyBuilder]

plugin = BuildpackPlugin()
```

### Multi-Hook Plugin

Implements multiple hooks:

```python
from hop3.core.hooks import hookimpl
from .docker_builder import DockerBuilder
from .docker_deployer import DockerDeployer

class DockerPlugin:
    name = "docker"

    @hookimpl
    def get_builders(self) -> list:
        return [DockerBuilder]

    @hookimpl
    def get_deployers(self) -> list:
        return [DockerDeployer]

plugin = DockerPlugin()
```

### Plugin with DI

Provides both strategies and DI providers:

```python
from dishka import Provider, provide, Scope
from hop3.core.hooks import hookimpl
from .postgres_service import PostgresService

class PostgresProvider(Provider):
    scope = Scope.APP

    @provide
    def get_postgres(self) -> PostgresService:
        return PostgresService()

class PostgresPlugin:
    name = "postgres"

    @hookimpl
    def get_addons(self) -> list:
        return [PostgresService]

    @hookimpl
    def get_di_providers(self) -> list:
        return [PostgresProvider()]

plugin = PostgresPlugin()
```

---

## Testing Hooks

### Testing Hook Registration

Verify your plugin is discovered and hooks are called:

```python
from hop3.core.plugins import get_plugin_manager

def test_plugin_registered():
    """Test that plugin hooks are called."""
    pm = get_plugin_manager()

    # Get all build strategies
    results = pm.hook.get_builders()
    strategies = [cls for sublist in results for cls in sublist]

    # Check our strategy is in the list
    strategy_names = [getattr(cls, "name", None) for cls in strategies]
    assert "my-builder" in strategy_names
```

### Testing Hook Implementations

Test the hook implementation directly:

```python
from my_plugin.plugin import MyPlugin

def test_get_build_strategies():
    """Test hook implementation returns correct strategies."""
    plugin = MyPlugin()
    strategies = plugin.get_builders()

    assert len(strategies) == 2
    assert strategies[0].name == "python"
    assert strategies[1].name == "node"
```

### Testing Strategy Discovery

Test that the core correctly discovers and uses your strategy:

```python
from hop3.core.plugins import get_build_strategy
from hop3.core.protocols import DeploymentContext

def test_strategy_discovery(tmp_path):
    """Test that build strategy is discovered and used."""
    # Create test app
    (tmp_path / "requirements.txt").write_text("flask==2.0.0")

    context = DeploymentContext(
        app_name="test",
        source_path=tmp_path,
        app_config={}
    )

    # Should find our Python builder
    strategy = get_build_strategy(context)
    assert strategy.name == "python"
```

---

## Common Pitfalls

### 1. Returning Instances Instead of Classes

**Wrong**:
```python
@hookimpl
def get_builders(self) -> list:
    return [MyBuilder(context)]  # ❌ No context available here
```

**Correct**:
```python
@hookimpl
def get_builders(self) -> list:
    return [MyBuilder]  # ✅ Return class
```

### 2. Forgetting to Register Plugin Instance

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

# Must instantiate for auto-registration
plugin = MyPlugin()
```

### 3. Not Importing Plugin

**Wrong**:
```python
# __init__.py
# Empty or doesn't import plugin
```

**Correct**:
```python
# __init__.py
from .plugin import plugin

__all__ = ["plugin"]
```

### 4. Incorrect Return Type

**Wrong**:
```python
@hookimpl
def get_builders(self) -> list:
    return MyBuilder  # ❌ Single class, not list
```

**Correct**:
```python
@hookimpl
def get_builders(self) -> list:
    return [MyBuilder]  # ✅ List of classes
```

### 5. Not Flattening Hook Results

**Wrong**:
```python
results = pm.hook.get_builders()
# results = [[Builder1, Builder2], [Builder3]]  ❌ List of lists
```

**Correct**:
```python
results = pm.hook.get_builders()
strategies = [cls for sublist in results for cls in sublist]
# strategies = [Builder1, Builder2, Builder3]  ✅ Flat list
```

---

## Advanced Hook Usage

### Conditional Strategy Registration

Only register strategies if certain conditions are met:

```python
@hookimpl
def get_builders(self) -> list:
    """Only provide Docker builder if Docker is available."""
    strategies = []

    if self._is_docker_available():
        strategies.append(DockerBuilder)

    return strategies

def _is_docker_available(self) -> bool:
    import shutil
    return shutil.which("docker") is not None
```

### Dynamic Strategy Generation

Generate strategies based on configuration:

```python
@hookimpl
def get_deployers(self) -> list:
    """Provide strategies based on config."""
    from hop3.config import HopConfig

    cfg = HopConfig.get_instance()
    strategies = [UWSGIDeployer]  # Always available

    if cfg.ENABLE_DOCKER:
        strategies.append(DockerDeployer)

    if cfg.ENABLE_SYSTEMD:
        strategies.append(SystemdDeployer)

    return strategies
```

### Hook Wrappers

Wrap other plugins' hooks (advanced):

```python
@hookimpl(hookwrapper=True)
def get_builders(self):
    """Wrap and modify other plugins' results."""
    # Get results from other plugins
    outcome = yield
    results = outcome.get_result()

    # Add our own strategies
    results.append([MyCustomBuilder])

    # Return modified results
    outcome.force_result(results)
```

---

## See Also

- [Plugin Development Guide](plugin-development.md) - How to create plugins
- [Protocol Reference](protocol-reference.md) - Strategy protocol specifications
- [External Plugin Guide](external-plugins.md) - Publishing external plugins
- [pluggy Documentation](https://pluggy.readthedocs.io/) - Hook system details
