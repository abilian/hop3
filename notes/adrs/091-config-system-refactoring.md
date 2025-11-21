# ADR 091: Configuration System Refactoring for Testability

Status: **Adopted**

## Introduction

This ADR proposes refactoring Hop3's configuration system from module-level constants to a more testable, flexible architecture that eliminates the need for monkeypatching in tests.

## Summary

Replace the current module-level constant configuration (`hop3/config.py`) with a configuration object that supports dependency injection, easier testing, and runtime configuration changes. This will eliminate the need for complex monkeypatching in tests while maintaining backward compatibility.

## Status

**Implemented**

## Context and Goals

### Context

**Current Implementation** (`packages/hop3-server/src/hop3/config.py`):

```python
# Module-level constants computed at import time
HOP3_ROOT = config.get_path("HOP3_ROOT", "/home/hop3")
APP_ROOT = HOP3_ROOT / "apps"
BACKUP_ROOT = HOP3_ROOT / "backups"
# ... many more derived paths

# Used throughout the codebase
from hop3 import config as c

class App:
    @property
    def app_path(self) -> Path:
        return c.APP_ROOT / self.name  # Uses module-level constant
```

**Problems with Current Approach:**

1. **Testing Complexity**: Tests require extensive monkeypatching to override config values:
   ```python
   # Current test setup - brittle and verbose
   monkeypatch.setattr(hop3.config, "HOP3_ROOT", tmp_path)
   monkeypatch.setattr(hop3.config, "APP_ROOT", tmp_path / "apps")
   monkeypatch.setattr(hop3.orm.app.c, "HOP3_ROOT", tmp_path)
   monkeypatch.setattr(hop3.orm.app.c, "APP_ROOT", tmp_path / "apps")
   ```

2. **Import-Time Evaluation**: Config values are computed when the module is imported, making them hard to change:
   ```python
   # These are computed ONCE at import time
   APP_ROOT = HOP3_ROOT / "apps"  # If HOP3_ROOT changes, APP_ROOT doesn't update
   ```

3. **Multiple Import References**: Different modules import config differently:
   ```python
   from hop3 import config as c      # Used in app.py
   import hop3.config                # Used in tests
   from hop3.config import HOP3_ROOT # Direct import
   ```

4. **No Runtime Reconfiguration**: Can't change configuration without module reloading

5. **Unclear Dependencies**: Hard to see what config values a component depends on

6. **Testing Anti-Pattern**: Recent test migration (ADR 090) highlighted this:
   > "I don't like monkeypatching the environment. Can we think of something more elegant?"

### Goals

1. **Testability**: Tests should easily provide custom config without monkeypatching
2. **Clarity**: Config dependencies should be explicit and traceable
3. **Flexibility**: Support multiple config sources (env vars, files, defaults)
4. **Backward Compatibility**: Minimize disruption to existing code
5. **Type Safety**: Maintain or improve type checking for config values
6. **Performance**: No significant runtime overhead
7. **Simplicity**: Don't over-engineer - keep it simple and Pythonic

## Tenets

1. **Explicit over Implicit**: Dependencies on configuration should be clear
2. **Testable by Default**: Tests shouldn't require hacks or workarounds
3. **Single Source of Truth**: One canonical way to access configuration
4. **Lazy Evaluation**: Derived values (like APP_ROOT) should update when base values change
5. **Backward Compatible**: Existing code should continue to work during migration

## Decision

**PROPOSED**: Implement a singleton configuration class with lazy property evaluation and support for dependency injection.

## Detailed Design

### Core Design: Configuration Class

```python
# packages/hop3-server/src/hop3/config.py

from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar

from hop3.lib.config import Config as ConfigLoader


class HopConfig:
    """Hop3 configuration with lazy evaluation and testability.

    This class provides:
    - Lazy property evaluation (derived values auto-update)
    - Dependency injection support for testing
    - Type-safe configuration access
    - Backward compatibility with module-level access

    Usage:
        # In production code
        from hop3.config import config
        app_path = config.APP_ROOT / "myapp"

        # In tests
        test_config = HopConfig(hop3_root=tmp_path)
        app = App(config=test_config)
    """

    # Class variable for global singleton instance
    _instance: ClassVar[HopConfig | None] = None

    def __init__(
        self,
        config_loader: ConfigLoader | None = None,
        hop3_root: Path | str | None = None,
    ):
        """Initialize configuration.

        Args:
            config_loader: Optional ConfigLoader instance (for file-based config)
            hop3_root: Optional override for HOP3_ROOT (useful for testing)
        """
        self._config_loader = config_loader or self._create_default_loader()
        self._hop3_root_override = Path(hop3_root) if hop3_root else None

    @staticmethod
    def _create_default_loader() -> ConfigLoader:
        """Create default config loader."""
        testing = "PYTEST_VERSION" in os.environ

        if not testing:
            hop3_root = Path(os.environ.get("HOP3_ROOT", "/home/hop3"))
            config_file = hop3_root / "hop3-server.toml"
            if config_file.exists():
                return ConfigLoader(file=config_file)

        return ConfigLoader()

    # Base Configuration Properties

    @property
    def HOP3_ROOT(self) -> Path:
        """Root directory for all Hop3 data."""
        if self._hop3_root_override:
            return self._hop3_root_override
        return self._config_loader.get_path("HOP3_ROOT", "/home/hop3")

    @property
    def HOP3_USER(self) -> str:
        """System user running Hop3."""
        return self._config_loader.get_str("HOP3_USER", "hop3")

    @property
    def MODE(self) -> str:
        """Operating mode: production, development, testing."""
        return self._config_loader.get_str("MODE", "production")

    @property
    def HOP3_DEBUG(self) -> bool:
        """Enable debug mode."""
        return self._config_loader.get_bool("HOP3_DEBUG", False)

    # Security Configuration

    @property
    def HOP3_SECRET_KEY(self) -> str:
        """Secret key for session encryption."""
        return self._config_loader.get_str("HOP3_SECRET_KEY", "")

    @property
    def HOP3_TOKEN_EXPIRY_HOURS(self) -> int:
        """JWT token expiry in hours."""
        return self._config_loader.get_int("HOP3_TOKEN_EXPIRY_HOURS", 24)

    @property
    def HOP3_UNSAFE(self) -> bool:
        """UNSAFE MODE: Disables authentication. USE ONLY FOR TESTING."""
        return self._config_loader.get_bool("HOP3_UNSAFE", False)

    # Proxy Configuration

    @property
    def HOP3_PROXY_TYPE(self) -> str:
        """Reverse proxy type: nginx, caddy, traefik."""
        return self._config_loader.get_str("HOP3_PROXY_TYPE", "nginx")

    # ACME Configuration

    @property
    def ACME_ENGINE(self) -> str:
        """ACME client engine: certbot, self-signed."""
        testing = "PYTEST_VERSION" in os.environ
        default = "self-signed" if testing else "certbot"
        return self._config_loader.get_str("ACME_ENGINE", default)

    @property
    def ACME_ROOT_CA(self) -> str:
        """ACME root certificate authority."""
        return self._config_loader.get_str("ACME_ROOT_CA", "letsencrypt.org")

    @property
    def ACME_EMAIL(self) -> str:
        """Email for ACME registration."""
        testing = "PYTEST_VERSION" in os.environ
        default = "test@example.com" if testing else "fixme@example.com"
        return self._config_loader.get_str("ACME_EMAIL", default)

    # Derived Paths (Lazy Evaluation)

    @property
    def HOP3_BIN(self) -> Path:
        """Binary directory."""
        return self.HOP3_ROOT / "bin"

    @property
    def HOP3_SCRIPT(self) -> str:
        """Path to hop-agent script."""
        return str(self.HOP3_ROOT / "venv" / "bin" / "hop-agent")

    @property
    def APP_ROOT(self) -> Path:
        """Root directory for all applications."""
        return self.HOP3_ROOT / "apps"

    @property
    def BACKUP_ROOT(self) -> Path:
        """Root directory for backups."""
        return self.HOP3_ROOT / "backups"

    @property
    def NGINX_ROOT(self) -> Path:
        """Nginx configuration directory."""
        return self.HOP3_ROOT / "nginx"

    @property
    def CACHE_ROOT(self) -> Path:
        """Cache directory."""
        return self.HOP3_ROOT / "cache"

    @property
    def CADDY_ROOT(self) -> Path:
        """Caddy configuration directory."""
        return self.HOP3_ROOT / "caddy"

    @property
    def TRAEFIK_ROOT(self) -> Path:
        """Traefik configuration directory."""
        return self.HOP3_ROOT / "traefik"

    @property
    def UWSGI_ROOT(self) -> Path:
        """uWSGI configuration root."""
        return self.HOP3_ROOT / "uwsgi"

    @property
    def UWSGI_AVAILABLE(self) -> Path:
        """uWSGI available configurations."""
        return self.HOP3_ROOT / "uwsgi-available"

    @property
    def UWSGI_ENABLED(self) -> Path:
        """uWSGI enabled configurations."""
        return self.HOP3_ROOT / "uwsgi-enabled"

    @property
    def UWSGI_LOG_MAXSIZE(self) -> str:
        """uWSGI log max size."""
        return "1048576"

    @property
    def ACME_WWW(self) -> Path:
        """ACME challenge directory."""
        return self.HOP3_ROOT / "acme"

    @property
    def ROOT_DIRS(self) -> list[Path]:
        """All root directories that should be created on setup."""
        return [
            self.APP_ROOT,
            self.BACKUP_ROOT,
            self.CACHE_ROOT,
            self.UWSGI_ROOT,
            self.UWSGI_AVAILABLE,
            self.UWSGI_ENABLED,
            self.NGINX_ROOT,
            self.ACME_WWW,
        ]

    # Utility Methods

    def get_parameters(self) -> dict[str, any]:
        """Get all configuration parameters as a dict.

        Useful for debugging and introspection.
        """
        return {
            name: getattr(self, name)
            for name in dir(self)
            if name.isupper() and not name.startswith("_")
        }

    @classmethod
    def get_instance(cls) -> HopConfig:
        """Get or create the global singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def set_instance(cls, instance: HopConfig) -> None:
        """Set the global singleton instance (useful for testing)."""
        cls._instance = instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the global singleton (useful for testing)."""
        cls._instance = None


# Global singleton instance (backward compatibility)
config = HopConfig.get_instance()

# Export commonly used values for backward compatibility
HOP3_ROOT = config.HOP3_ROOT
APP_ROOT = config.APP_ROOT
BACKUP_ROOT = config.BACKUP_ROOT
# ... etc for all other constants

# Note: These module-level exports are deprecated and will be removed in a future version
# New code should use: from hop3.config import config
```

### Migration Strategy

**Phase 1: Add New System (Backward Compatible)**

1. Add `HopConfig` class to `config.py`
2. Keep existing module-level constants for compatibility
3. Update constants to reference config instance:
   ```python
   config = HopConfig.get_instance()
   HOP3_ROOT = config.HOP3_ROOT  # Delegates to config object
   ```

**Phase 2: Migrate Core Components**

1. Update `App` model to accept optional config:
   ```python
   class App(BigIntAuditBase):
       def __init__(self, name: str, config: HopConfig | None = None):
           self.name = name
           self._config = config or HopConfig.get_instance()

       @property
       def app_path(self) -> Path:
           return self._config.APP_ROOT / self.name
   ```

2. Update other core classes similarly

**Phase 3: Update Tests**

Replace monkeypatching with clean config injection:

```python
# OLD (monkeypatching)
@pytest.fixture
def test_client(tmp_path, monkeypatch):
    monkeypatch.setattr(hop3.config, "HOP3_ROOT", tmp_path)
    monkeypatch.setattr(hop3.config, "APP_ROOT", tmp_path / "apps")
    monkeypatch.setattr(hop3.orm.app.c, "HOP3_ROOT", tmp_path)
    monkeypatch.setattr(hop3.orm.app.c, "APP_ROOT", tmp_path / "apps")
    # ...

# NEW (clean injection)
@pytest.fixture
def test_config(tmp_path):
    """Provide test configuration with tmp_path."""
    return HopConfig(hop3_root=tmp_path)

@pytest.fixture
def test_client(test_config):
    """Create test client with custom config."""
    # Set as global instance for components that use get_instance()
    HopConfig.set_instance(test_config)

    # Components that accept config will use test_config
    app = create_app(config=test_config)
    client = TestClient(app)

    yield client

    # Cleanup
    HopConfig.reset_instance()
```

**Phase 4: Deprecate Module-Level Constants**

1. Add deprecation warnings to module-level constants
2. Update documentation to use `config` object
3. Migrate remaining code

**Phase 5: Remove Module-Level Constants**

1. Remove deprecated constants
2. Update imports across codebase

### Alternative: Minimal Refactoring

If full refactoring is too large, a simpler approach:

```python
# Simpler version - just make paths properties of a class

class _ConfigPaths:
    """Lazy evaluation of config paths."""

    def __init__(self):
        self._loader = ConfigLoader()
        self._hop3_root_override = None

    def set_hop3_root(self, path: Path) -> None:
        """Override HOP3_ROOT (for testing)."""
        self._hop3_root_override = path

    @property
    def HOP3_ROOT(self) -> Path:
        if self._hop3_root_override:
            return self._hop3_root_override
        return self._loader.get_path("HOP3_ROOT", "/home/hop3")

    @property
    def APP_ROOT(self) -> Path:
        return self.HOP3_ROOT / "apps"  # Auto-updates when HOP3_ROOT changes!

    # ... other paths

# Global instance
config = _ConfigPaths()

# Tests just call:
config.set_hop3_root(tmp_path)
```

## Examples and Interactions

### Example 1: Production Usage

```python
# Application code
from hop3.config import config

def setup_application(app_name: str):
    app_dir = config.APP_ROOT / app_name
    app_dir.mkdir(parents=True, exist_ok=True)

    # Config values are always fresh
    if config.HOP3_DEBUG:
        print(f"Creating app at {app_dir}")
```

### Example 2: Testing with Custom Config

```python
# Test code
def test_app_creation(tmp_path):
    # Create test config
    test_config = HopConfig(hop3_root=tmp_path)

    # Use in tests
    assert test_config.APP_ROOT == tmp_path / "apps"
    assert test_config.BACKUP_ROOT == tmp_path / "backups"

    # All derived paths auto-update
    app_path = test_config.APP_ROOT / "test-app"
    assert str(app_path).startswith(str(tmp_path))
```

### Example 3: Dependency Injection

```python
# Domain model with optional config
class App:
    def __init__(self, name: str, config: HopConfig | None = None):
        self.name = name
        self._config = config or HopConfig.get_instance()

    @property
    def app_path(self) -> Path:
        return self._config.APP_ROOT / self.name

# Production: uses global config
app = App("myapp")

# Testing: uses custom config
test_config = HopConfig(hop3_root=tmp_path)
app = App("myapp", config=test_config)
```

### Example 4: Before/After Comparison

**Current System (Before)**:

```python
# config.py
HOP3_ROOT = config.get_path("HOP3_ROOT", "/home/hop3")
APP_ROOT = HOP3_ROOT / "apps"  # Computed once at import

# test
def test_app_create(tmp_path, monkeypatch):
    monkeypatch.setattr(hop3.config, "HOP3_ROOT", tmp_path)
    monkeypatch.setattr(hop3.config, "APP_ROOT", tmp_path / "apps")
    monkeypatch.setattr(hop3.orm.app.c, "HOP3_ROOT", tmp_path)
    monkeypatch.setattr(hop3.orm.app.c, "APP_ROOT", tmp_path / "apps")
    # Still might not work due to import timing!
```

**New System (After)**:

```python
# config.py
config = HopConfig.get_instance()

# test
def test_app_create(tmp_path):
    test_config = HopConfig(hop3_root=tmp_path)
    HopConfig.set_instance(test_config)

    # All code using config.APP_ROOT will see tmp_path/apps
    # No monkeypatching needed!
```

## Consequences

### Benefits

1. **Eliminates Monkeypatching**: Tests use clean dependency injection
2. **Lazy Evaluation**: Derived paths auto-update when base paths change
3. **Clear Dependencies**: Easy to see what config values are used
4. **Type Safe**: Properties have clear return types
5. **Testable**: Each component can have its own config instance
6. **Flexible**: Supports multiple config sources
7. **Introspectable**: Can dump all config values for debugging
8. **Backward Compatible**: Existing code continues to work during migration

### Drawbacks

1. **Migration Effort**: Need to update many files across codebase
2. **Breaking Change**: Eventually removes module-level constants
3. **Slight Overhead**: Property access instead of direct attribute access (negligible)
4. **Learning Curve**: Team needs to learn new pattern
5. **Singleton Complexity**: Global singleton can be tricky in some edge cases
6. **More Lines of Code**: Properties are more verbose than constants

## Lessons Learned

### From Current Test Issues

The dashboard UI tests (ADR 090) revealed the pain of monkeypatching:
- Had to patch 4+ different locations
- Still didn't work until we also mocked `App.create()`
- Tests broke when import order changed
- User feedback: "I don't like monkeypatching the environment"

### From Other Projects

**Django**: Uses a similar `settings` object with lazy evaluation
```python
from django.conf import settings
# settings.MEDIA_ROOT auto-updates based on BASE_DIR
```

**Flask**: Uses app context with config
```python
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = '/tmp'
# Tests override via app.config.update()
```

**FastAPI**: Uses dependency injection
```python
def get_config() -> Config:
    return Config()

@app.get("/")
def index(config: Config = Depends(get_config)):
    # Tests override the dependency
```

## Action Items

### Phase 1: Proposal and Design (1-2 days)

1. ✅ Write this ADR
2. Review and get feedback
3. Refine design based on feedback
4. Create implementation plan

### Phase 2: Core Implementation (3-5 days)

1. Create `HopConfig` class in `config.py`
2. Add backward-compatible module-level exports
3. Write comprehensive tests for config class
4. Update documentation

### Phase 3: Migrate Core Components (5-7 days)

1. Update `App` model to accept config parameter
2. Update `create_app()` in server to accept config
3. Update other core components (builders, deployers, etc.)
4. Ensure all tests pass with both old and new systems

### Phase 4: Migrate Tests (3-5 days)

1. Create reusable test fixtures (`test_config`, `test_app_with_config`)
2. Migrate system tests to use new fixtures
3. Migrate integration tests
4. Remove monkeypatching from all tests

### Phase 5: Documentation and Deprecation (2-3 days)

1. Update developer documentation
2. Add migration guide
3. Add deprecation warnings to old constants
4. Update testing strategy guide

### Phase 6: Cleanup (2-3 days)

1. Remove deprecated module-level constants
2. Remove backward compatibility shims
3. Final documentation update

**Total Estimated Effort**: 15-25 days

## Alternatives

### Alternative 1: Keep Current System, Add Helper Functions

```python
# Minimal change - just add test helpers
def with_test_config(hop3_root: Path):
    """Context manager for test config."""
    import hop3.config
    original_root = hop3.config.HOP3_ROOT
    hop3.config.HOP3_ROOT = hop3_root
    hop3.config.APP_ROOT = hop3_root / "apps"
    # ... update all derived paths
    try:
        yield
    finally:
        hop3.config.HOP3_ROOT = original_root
        # ... restore all paths
```

**Pros**: Minimal change, no migration needed
**Cons**: Still uses globals, still brittle, doesn't solve root problem

### Alternative 2: Environment Variable Only

```python
# Just use environment variables everywhere
@pytest.fixture
def test_env(tmp_path, monkeypatch):
    monkeypatch.setenv("HOP3_ROOT", str(tmp_path))
    # Reload all modules that use HOP3_ROOT
    ...
```

**Pros**: Simple, standard approach
**Cons**: Requires module reloading, still brittle, environment pollution

### Alternative 3: Full Dependency Injection Framework

Use a DI framework like `dependency-injector`:

```python
from dependency_injector import containers, providers

class Container(containers.DeclarativeContainer):
    config = providers.Singleton(HopConfig)
    app_service = providers.Factory(AppService, config=config)
```

**Pros**: Industry standard, very flexible
**Cons**: Heavy dependency, steep learning curve, over-engineered for our needs

**Rejected**: Too complex for Hop3's needs

### Alternative 4: Pydantic Settings

Use Pydantic's `BaseSettings`:

```python
from pydantic_settings import BaseSettings

class HopConfig(BaseSettings):
    hop3_root: Path = Path("/home/hop3")

    @property
    def app_root(self) -> Path:
        return self.hop3_root / "apps"

    class Config:
        env_prefix = "HOP3_"
```

**Pros**: Type validation, environment variable support
**Cons**: External dependency, validation overhead

**Consideration**: Could be used as the `ConfigLoader` implementation

## Prior Art

### Django Settings

Django uses a lazy settings object:

```python
# django/conf/__init__.py
class LazySettings:
    def __getattr__(self, name):
        if self._wrapped is empty:
            self._setup()
        return getattr(self._wrapped, name)

settings = LazySettings()
```

Our design borrows this lazy evaluation concept.

### Flask Config

Flask uses a dict-like config object:

```python
app = Flask(__name__)
app.config['DEBUG'] = True

# Testing
app.config.update(TEST_CONFIG)
```

Simpler but less type-safe than our approach.

### Pytest Fixtures

Pytest's fixture system is our inspiration for dependency injection:

```python
@pytest.fixture
def app_config(tmp_path):
    return HopConfig(hop3_root=tmp_path)

def test_something(app_config):
    assert app_config.APP_ROOT == ...
```

## Unresolved Questions

1. **Singleton vs Instance**: Should we primarily use singleton pattern or pass instances?
   - **Proposed**: Singleton for production, instances for testing

2. **Property vs Method**: Should config values be properties or methods?
   - **Proposed**: Properties for simple values, methods if computation is expensive

3. **Caching**: Should we cache computed values or always recompute?
   - **Proposed**: No caching - properties are cheap, and we want fresh values

4. **Thread Safety**: Do we need thread-safe config access?
   - **Proposed**: Not initially - config is read-only after initialization in practice

5. **Config Validation**: Should we validate config values on initialization?
   - **Proposed**: Yes, but only critical values (HOP3_ROOT exists, etc.)

6. **Environment Variable Override**: Should env vars always override file config?
   - **Proposed**: Yes, following 12-factor app principles

7. **Backward Compatibility Period**: How long to support old module-level constants?
   - **Proposed**: Two minor versions (e.g., 0.5.0 deprecate, 0.7.0 remove)

## Future Work

### Enhanced Configuration Features

1. **Config Validation**: Add schema validation using Pydantic
2. **Config Profiles**: Support dev/staging/prod profiles
3. **Dynamic Reload**: Support reloading config without restart
4. **Config Merging**: Layer multiple config sources (defaults < file < env < override)
5. **Config Documentation**: Auto-generate config reference from properties

### Testing Improvements

1. **Config Fixtures Library**: Shared fixtures for common test scenarios
2. **Config Factories**: Factory functions for creating test configs
3. **Config Assertions**: Custom assertions for config validation
4. **Config Mocking**: Helper utilities for mocking specific config values

### Developer Experience

1. **CLI Tool**: `hop3 config show` to display current config
2. **Config Validation**: `hop3 config validate` to check config file
3. **Config Export**: `hop3 config export` to generate config template
4. **Type Stubs**: Generate `.pyi` files for better IDE support

## Related

- **ADR 090**: Dashboard UI Test Classification - Highlighted monkeypatching pain
- **ADR 001-003**: Original config system ADRs
- **Testing Strategy** (`docs/src/dev/testing-strategy.md`) - Will need updates

## References

1. **12-Factor App Configuration**: https://12factor.net/config
2. **Django Settings**: https://docs.djangoproject.com/en/stable/topics/settings/
3. **Flask Configuration**: https://flask.palletsprojects.com/en/stable/config/
4. **Pydantic Settings**: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
5. **Martin Fowler - Dependency Injection**: https://martinfowler.com/articles/injection.html
6. **Python Singleton Patterns**: https://python-patterns.guide/gang-of-four/singleton/

## Notes

### Implementation Priority

The migration can be done incrementally:

1. **High Priority** (needed for test cleanup):
   - Core config class
   - App model migration
   - Test fixtures

2. **Medium Priority** (improves DX):
   - Server/builder/deployer migration
   - Documentation updates
   - CLI tools

3. **Low Priority** (nice to have):
   - Advanced features (validation, profiles)
   - Deprecation and cleanup
   - Full type stub generation

### Risks and Mitigations

**Risk**: Large-scale refactoring might introduce bugs
- **Mitigation**: Incremental migration with both systems working in parallel

**Risk**: Tests might break during migration
- **Mitigation**: Keep old test patterns working until migration complete

**Risk**: Performance regression from property access
- **Mitigation**: Benchmark before/after, add caching if needed (unlikely)

**Risk**: Team resistance to new pattern
- **Mitigation**: Good documentation, pair programming, gradual rollout

## Appendix

### Full Example: Before and After

**Before (Current System)**:

```python
# config.py
HOP3_ROOT = config.get_path("HOP3_ROOT", "/home/hop3")
APP_ROOT = HOP3_ROOT / "apps"

# app.py
from hop3 import config as c

class App:
    @property
    def app_path(self):
        return c.APP_ROOT / self.name

# test_app_create.py
def test_app_create(tmp_path, monkeypatch):
    import hop3.config
    import hop3.orm.app
    monkeypatch.setattr(hop3.config, "HOP3_ROOT", tmp_path)
    monkeypatch.setattr(hop3.config, "APP_ROOT", tmp_path / "apps")
    monkeypatch.setattr(hop3.orm.app.c, "HOP3_ROOT", tmp_path)
    monkeypatch.setattr(hop3.orm.app.c, "APP_ROOT", tmp_path / "apps")

    app = App(name="test")
    # Might still not work!
```

**After (New System)**:

```python
# config.py
class HopConfig:
    @property
    def HOP3_ROOT(self):
        return self._loader.get_path("HOP3_ROOT", "/home/hop3")

    @property
    def APP_ROOT(self):
        return self.HOP3_ROOT / "apps"  # Lazy!

config = HopConfig.get_instance()

# app.py
from hop3.config import config

class App:
    def __init__(self, name, config=None):
        self.name = name
        self._config = config or HopConfig.get_instance()

    @property
    def app_path(self):
        return self._config.APP_ROOT / self.name

# test_app_create.py
def test_app_create(tmp_path):
    test_config = HopConfig(hop3_root=tmp_path)
    app = App(name="test", config=test_config)

    assert app.app_path == tmp_path / "apps" / "test"
    # Works perfectly!
```

### Size Comparison

**Lines of Code Impact**:

- New `HopConfig` class: ~250 lines
- Updated imports: ~50 files × 1 line = 50 lines
- Updated App model: ~10 lines
- Updated tests: ~30 files × -5 lines = -150 lines (simpler!)

**Net**: +160 lines, but much cleaner and more maintainable

### Performance Benchmark

Preliminary estimates (to be measured):

```python
# Current: Direct attribute access
# ~5ns per access

# New: Property access
# ~50ns per access (10x slower)

# Impact: Negligible
# Config accessed ~1000 times per request
# Overhead: 45 microseconds per request
# Acceptable for 99.9% of use cases
```
