# ADR 028: Pluggy + Dishka Integration for Plugin-Contributed Services

**Status**: Final
**Type**: Feature
**Created**: 2025-11-20
**Authors**: Stefane Fermigier
**Related-ADRs**: 020

## Context

Hop3 uses two complementary frameworks:
- **Pluggy**: Plugin system for discovering and executing extension points
- **Dishka**: Dependency injection framework for managing service lifecycles

Absent an integration between them, these systems operate independently:
- Plugins register via Pluggy's hook system
- Services are managed via Dishka's container and providers
- No mechanism lets plugins contribute services to the DI container

This separation creates several problems:

### Problem 1: Manual Service Registration
Plugins had to manually register services using global registries or singletons:

```python
# Anti-pattern: Global service registration
from hop3.services import register_service

register_service("postgres", PostgresService())
```

This approach:
- Runs at import time (order-dependent)
- Creates global state
- Is difficult to test
- Bypasses Dishka's lifecycle management

### Problem 2: No Dependency Injection for Plugin Services
Plugin services couldn't leverage Dishka's features:
- No automatic dependency resolution
- No scope management (APP vs REQUEST)
- No type-safe injection
- Manual lifecycle management

### Problem 3: Tight Coupling
To use a plugin service, code had to:
1. Know the service exists globally
2. Import from the plugin module directly
3. Handle instantiation manually

This made plugins harder to test and created tight coupling between core and plugins.

### Design Goals

We needed a solution that:
1. Allows plugins to contribute services to the DI container
2. Maintains separation between Pluggy (discovery) and Dishka (DI)
3. Supports dependency injection between plugin services
4. Preserves type safety
5. Remains testable
6. Follows both frameworks' best practices

## Decision

We integrate Pluggy with Dishka using a **hook-based provider registration pattern**, where:

1. **Plugins contribute Dishka providers via a Pluggy hook**
2. **Container creation collects providers from all plugins**
3. **Services are injected using standard Dishka mechanisms**

### Architecture

```
┌─────────────────┐
│  Plugin System  │
│    (Pluggy)     │
└────────┬────────┘
         │
         │ get_di_providers() hook
         │
         ├──► Plugin A → ProviderA
         ├──► Plugin B → ProviderB
         └──► Plugin C → ProviderC
                    │
                    ▼
         ┌──────────────────┐
         │  DI Container    │
         │    (Dishka)      │
         │                  │
         │ • ConfigProvider │
         │ • CoreProviders  │
         │ • ProviderA      │
         │ • ProviderB      │
         │ • ProviderC      │
         └──────────────────┘
```

### Detailed Design

#### 1. Hook Specification

The `get_di_providers()` hook in `hop3/core/hookspecs.py`:

```python
@hookspec
def get_di_providers() -> list:
    """Get DI providers from this plugin.

    Returns:
        List of Dishka Provider instances
    """
```

#### 2. Container Integration

Container creation in `hop3/di/container.py`:

```python
def _get_plugin_providers() -> list:
    """Collect DI providers from all registered plugins."""
    pm = get_plugin_manager()
    provider_lists = pm.hook.get_di_providers()
    return [provider for sublist in provider_lists for provider in sublist]

def create_container() -> Container:
    providers = [
        ConfigProvider(),
        HopServicesProvider(),
    ]
    plugin_providers = _get_plugin_providers()
    providers.extend(plugin_providers)
    return make_container(*providers)
```

#### 3. Plugin Implementation Pattern

Plugins implement the hook to contribute providers:

```python
# myapp_plugin/plugin.py
from dishka import Provider, provide, Scope
from hop3.core.hooks import hop3_hook_impl

class MyPluginProvider(Provider):
    scope = Scope.APP

    @provide
    def get_my_service(self, config: HopConfig) -> MyService:
        return MyService(config.setting)

@hop3_hook_impl
def get_di_providers() -> list:
    return [MyPluginProvider()]
```

### Usage Patterns

#### CLI Context
```python
from hop3.di import create_container

container = create_container()
try:
    service = container.get(MyService)  # From plugin
    service.do_work()
finally:
    container.close()
```

#### Web Context
```python
from dishka.integrations.starlette import FromDishka, inject

@inject
async def my_view(service: FromDishka[MyService]):
    """Service from plugin automatically injected."""
    return service.do_work()
```

## Consequences

### Positive

1. **Clean Separation of Concerns**
   - Pluggy handles plugin discovery and registration
   - Dishka handles service lifecycle and injection
   - Each framework does what it's best at

2. **Automatic Discovery**
   - Plugins register providers via hooks
   - Container creation automatically collects them
   - No manual registration needed

3. **Type-Safe Dependency Injection**
   - Full type checking with mypy/pyright
   - IDE autocompletion for injected services
   - Runtime type validation via Dishka

4. **Dependency Injection Between Plugins**
   - Plugin A can depend on services from Plugin B
   - Dishka resolves the dependency graph
   - Clear, declarative dependencies

5. **Proper Lifecycle Management**
   - Services use Dishka scopes (APP, REQUEST)
   - Automatic cleanup via context managers
   - No manual singleton management

6. **Testability**
   - Easy to create containers with mock providers
   - Can test plugins in isolation
   - No global state to manage

7. **Backwards Compatible**
   - Existing code continues to work
   - Plugins can migrate incrementally
   - No breaking changes

### Negative

1. **Increased Complexity**
   - Developers must understand both Pluggy and Dishka
   - More indirection (hook → provider → service)
   - Learning curve for new contributors

2. **Import-Time Plugin Discovery**
   - Plugins are discovered at import time
   - All plugins load even if not used
   - Could be slow with many plugins (mitigated by lazy imports)

3. **No Provider Validation**
   - Invalid providers only fail at runtime
   - No compile-time checks for provider compatibility
   - Could add validation in future

4. **Circular Dependency Risk**
   - `container.py` imports `plugins.py` at runtime
   - Mitigated by lazy import inside function
   - Must be careful about import order

### Neutral

1. **Two Frameworks Instead of One**
   - Could use pure Dishka or pure Pluggy
   - But combination leverages strengths of both
   - Industry pattern (e.g., pytest uses Pluggy + fixtures)

2. **Hook Returns List**
   - Follows Pluggy best practices
   - Allows plugins to return multiple providers
   - Requires flattening list of lists

## Alternatives Considered

### Alternative 1: Global Service Registry

```python
# Anti-pattern
services = {}

def register_service(name, instance):
    services[name] = instance

def get_service(name):
    return services[name]
```

**Rejected because**:
- Global mutable state
- No type safety
- No dependency injection
- Hard to test

### Alternative 2: Pure Dishka (No Pluggy)

Use entry points directly in Dishka:

```python
def create_container():
    providers = [ConfigProvider()]

    # Load providers from entry points
    for ep in entry_points(group="hop3.providers"):
        provider = ep.load()
        providers.append(provider())

    return make_container(*providers)
```

**Rejected because**:
- Loses Pluggy's hook system
- No way to contribute build strategies, OS handlers, etc.
- Would need to rebuild plugin infrastructure
- Inconsistent with existing architecture

### Alternative 3: Pure Pluggy (No Dishka)

Plugins provide factories via hooks:

```python
@hookspec
def get_services() -> dict:
    """Return service name → instance mapping."""

@hookimpl
def get_services():
    return {"postgres": PostgresService()}
```

**Rejected because**:
- Manual lifecycle management
- No automatic dependency resolution
- No type-safe injection
- Would have to rebuild DI features

### Alternative 4: Dependency Injection in Pluggy Hooks

Pass container to hooks, let plugins get services:

```python
@hookspec
def initialize_plugin(container):
    """Plugin can get services from container."""

@hookimpl
def initialize_plugin(container):
    config = container.get(HopConfig)
    # Use config...
```

**Rejected because**:
- Inversion of control is backwards
- Plugins become tightly coupled to container
- Doesn't allow plugins to contribute services
- Less declarative than providers

### Alternative 5: Hybrid Registry + DI

Plugins register factories, DI system calls them:

```python
@hookimpl
def register_services():
    return {
        "postgres": lambda config: PostgresService(config)
    }
```

**Rejected because**:
- More complex than provider pattern
- Loses Dishka's declarative providers
- Still requires custom integration code
- Less type-safe

## Related Decisions

- **ADR 027**: Config System Refactoring — Dishka manages configuration.
- Dishka replaces wireup as the dependency-injection framework.
- The global container singleton is removed in favour of explicitly created containers.

## Implementation Notes

### Migration Path

Plugins move from global registration to provider contribution:

**Before**:
```python
# Old approach
register_service("postgres", PostgresService())
```

**After**:
```python
# New approach
class PostgresProvider(Provider):
    scope = Scope.APP

    @provide
    def get_postgres_service(self) -> PostgresService:
        return PostgresService()

@hop3_hook_impl
def get_di_providers() -> list:
    return [PostgresProvider()]
```

### Testing Strategy

Test plugin provider integration:

```python
def test_plugin_contributes_provider():
    container = create_container()
    try:
        service = container.get(PostgresService)
        assert service is not None
    finally:
        container.close()
```

Test with mock providers:

```python
@pytest.fixture
def container_with_mock():
    class MockProvider(Provider):
        @provide
        def get_service(self) -> Service:
            return Mock(spec=Service)

    return make_container(MockProvider())
```

### Performance Considerations

- Plugin discovery happens once at startup
- Provider collection is O(n) where n = number of plugins
- Service resolution is cached by Dishka
- Lazy imports keep plugin load fast

## References

- [Pluggy Documentation](https://pluggy.readthedocs.io/)
- [Dishka Documentation](https://dishka.readthedocs.io/)
