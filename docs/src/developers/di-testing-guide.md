# Dependency Injection Testing Guide

## Overview

This guide covers best practices for testing Hop3 code that uses Dishka dependency injection. It provides patterns for clean, maintainable tests that avoid common pitfalls like excessive mocking, environment manipulation, and unnecessary try/finally blocks.

## Core Principles

### 1. Use Real Services, Not Mocks

**Bad**:
```python
from unittest.mock import Mock

def test_backup_manager():
    mock_session = Mock(spec=Session)
    manager = BackupManager(mock_session)
    # Testing mock interactions, not real behavior
```

**Good**:
```python
def test_backup_manager(di_container):
    """Test BackupManager with real database session."""
    with di_container() as request_container:
        manager = request_container.get(BackupManager)
        # Testing real behavior with in-memory database
```

### 2. Use Pytest Fixtures for Container Management

**Bad**:
```python
def test_service():
    container = create_container()
    try:
        service = container.get(MyService)
        assert service is not None
    finally:
        container.close()
```

**Good**:
```python
@pytest.fixture
def container():
    """Create container with proper cleanup."""
    container = create_container()
    yield container
    container.close()

def test_service(container):
    service = container.get(MyService)
    assert isinstance(service, MyService)
```

### 3. No Environment Manipulation in Tests

**Bad**:
```python
import os

def test_with_config():
    os.environ["HOP3_SETTING"] = "value"
    try:
        # test code
        pass
    finally:
        os.environ.pop("HOP3_SETTING", None)
```

**Good**:
```python
@pytest.fixture(autouse=True)
def setup_config():
    """Configure environment for all tests in module."""
    os.environ["HOP3_SETTING"] = "value"
    yield
    os.environ.pop("HOP3_SETTING", None)

def test_with_config():
    # Environment already configured by fixture
    pass
```

## Standard Test Fixtures

### The `di_container` Fixture

Located in `packages/hop3-server/tests/di_fixtures.py`, this fixture provides a fully configured DI container with in-memory database:

```python
@pytest.fixture
def di_container() -> Container:
    """Create a DI container for testing.

    This fixture provides a fresh Dishka container for each test,
    ensuring test isolation.

    Uses in-memory SQLite database for testing to avoid side effects.

    Yields:
        Container: A fresh Dishka container with all providers registered

    Example:
        def test_my_service(di_container):
            service = di_container.get(MyService)
            assert service is not None
    """
    os.environ["HOP3_DATABASE_URI"] = "sqlite:///:memory:"

    try:
        container = make_container(
            ConfigProvider(),
            DatabaseProvider(),
            HopServicesProvider(),
        )

        yield container
        container.close()
    finally:
        os.environ.pop("HOP3_DATABASE_URI", None)
```

**Usage**:

```python
# For APP scope services (singletons)
def test_certificates_manager(di_container):
    manager = di_container.get(CertificatesManager)
    assert isinstance(manager, CertificatesManager)

# For REQUEST scope services (per-request instances)
def test_backup_manager(di_container):
    with di_container() as request_container:
        manager = request_container.get(BackupManager)
        assert isinstance(manager, BackupManager)
```

## Testing Patterns by Service Scope

### APP Scope Services

APP scope services are singletons - one instance per container lifetime.

**Examples**: `CertificatesManager`, `PostgresAdmin`, `RedisClientFactory`

```python
def test_service_is_singleton(di_container):
    """Test that APP scope service is a singleton."""
    service1 = di_container.get(MyService)
    service2 = di_container.get(MyService)

    assert service1 is service2
```

### REQUEST Scope Services

REQUEST scope services get a fresh instance per request/operation.

**Examples**: `BackupManager` (needs fresh database session)

```python
def test_service_from_container(di_container):
    """Test that REQUEST scope service can be retrieved."""
    with di_container() as request_container:
        service = request_container.get(MyService)
        assert isinstance(service, MyService)

def test_service_is_fresh_per_request(di_container):
    """Test that each request gets a fresh instance."""
    with di_container() as request1:
        service1 = request1.get(MyService)

    with di_container() as request2:
        service2 = request2.get(MyService)

    assert service1 is not service2
```

## Testing Plugin-Provided Services

Plugins contribute services via the `get_di_providers()` hook. To test these, you need a container that loads plugins:

```python
@pytest.fixture
def container():
    """Create container with plugin providers."""
    container = create_container()  # Loads plugins
    yield container
    container.close()

def test_plugin_service(container):
    """Test service provided by plugin."""
    service = container.get(PluginService)
    assert isinstance(service, PluginService)
```

**Note**: The `di_container` fixture does NOT load plugins (it creates a minimal container). Use `create_container()` when you need plugin services.

## Common Test Patterns

### Pattern 1: Testing Service Functionality

```python
def test_backup_manager_creates_backup(di_container):
    """Test BackupManager can create backups."""
    with di_container() as request_container:
        manager = request_container.get(BackupManager)

        # Create test app
        app = App.create(name="test-app")

        # Test backup creation
        backup_id, path = manager.create_backup(app)

        assert backup_id is not None
        assert path.exists()
```

### Pattern 2: Testing Service Configuration

```python
def test_redis_factory_from_config():
    """Test RedisClientFactory uses config correctly."""
    config = Config(env_prefix="REDIS_")
    factory = RedisClientFactory.from_config(config)

    assert factory.host == "localhost"
    assert factory.port == 6379
```

### Pattern 3: Testing Service Dependencies

```python
def test_service_gets_real_dependencies(di_container):
    """Test that service receives real injected dependencies."""
    with di_container() as request_container:
        manager = request_container.get(BackupManager)

        # Verify injected session is real SQLAlchemy session
        assert hasattr(manager.db_session, "query")
        assert hasattr(manager.db_session, "commit")
```

### Pattern 4: Testing Container Isolation

```python
@pytest.fixture
def two_containers():
    """Create two separate containers for isolation testing."""
    container1 = create_container()
    container2 = create_container()
    yield container1, container2
    container1.close()
    container2.close()

def test_containers_are_isolated(two_containers):
    """Test that different containers have isolated services."""
    container1, container2 = two_containers

    service1 = container1.get(MyService)
    service2 = container2.get(MyService)

    # Different containers = different singletons
    assert service1 is not service2
```

## Anti-Patterns to Avoid

### ❌ Don't Mock Services That Can Be Real

```python
# BAD
from unittest.mock import Mock

class MockProvider(Provider):
    @provide
    def get_service(self) -> MyService:
        return Mock(spec=MyService)

# GOOD
# Use real service with in-memory database
def test_service(di_container):
    service = di_container.get(MyService)
```

### ❌ Don't Use try/finally for Container Cleanup

```python
# BAD
def test_service():
    container = create_container()
    try:
        service = container.get(MyService)
    finally:
        container.close()

# GOOD
@pytest.fixture
def container():
    container = create_container()
    yield container
    container.close()

def test_service(container):
    service = container.get(MyService)
```

### ❌ Don't Manipulate Environment in Tests

```python
# BAD
def test_with_config():
    os.environ["KEY"] = "value"
    try:
        test_code()
    finally:
        os.environ.pop("KEY", None)

# GOOD
@pytest.fixture(autouse=True)
def setup_env():
    os.environ["KEY"] = "value"
    yield
    os.environ.pop("KEY", None)
```

### ❌ Don't Test Mock Interactions

```python
# BAD - Tests mocking, not real behavior
def test_service_calls_method():
    mock = Mock(spec=MyService)
    mock.do_work.return_value = "result"
    result = mock.do_work()
    mock.do_work.assert_called_once()

# GOOD - Tests real behavior
def test_service_does_work(di_container):
    service = di_container.get(MyService)
    result = service.do_work()
    assert result == expected_result
```

## Example: Complete Test Module

Here's a complete example showing clean DI testing patterns:

```python
# tests/a_unit/services/test_my_service.py

from hop3.services import MyService
from hop3.di import create_container
import pytest


def test_service_from_container(di_container):
    """Test that MyService can be retrieved from DI container."""
    service = di_container.get(MyService)
    assert isinstance(service, MyService)


def test_service_is_singleton(di_container):
    """Test that MyService is a singleton in APP scope."""
    service1 = di_container.get(MyService)
    service2 = di_container.get(MyService)
    assert service1 is service2


def test_service_functionality(di_container):
    """Test that MyService performs its function."""
    service = di_container.get(MyService)
    result = service.process_data("input")
    assert result == "expected output"


@pytest.fixture
def container_with_plugins():
    """Create container that loads plugin providers."""
    container = create_container()
    yield container
    container.close()


def test_service_from_plugin(container_with_plugins):
    """Test service provided by plugin."""
    service = container_with_plugins.get(PluginService)
    assert isinstance(service, PluginService)
```

## Testing Service Lifecycle

### Testing Resource Cleanup

For services that manage resources (files, connections, etc.), test that REQUEST scope properly cleans up:

```python
def test_session_cleanup(di_container):
    """Test that database sessions are properly closed."""
    # First request
    with di_container() as request1:
        manager1 = request1.get(BackupManager)
        session1 = manager1.db_session
        assert not session1.closed

    # Session should be closed after context exit
    assert session1.closed

    # Second request gets fresh session
    with di_container() as request2:
        manager2 = request2.get(BackupManager)
        session2 = manager2.db_session
        assert session1 is not session2
        assert not session2.closed
```

## Best Practices Summary

1. ✅ **Use `di_container` fixture** for services that don't need plugins
2. ✅ **Use `create_container()` fixture** for plugin-provided services
3. ✅ **Test with real services** using in-memory database
4. ✅ **Use pytest fixtures** for setup/teardown
5. ✅ **Use `autouse=True` fixtures** for environment setup
6. ✅ **Test real behavior**, not mock interactions
7. ✅ **Keep tests simple** - one assertion per test when possible
8. ✅ **Use descriptive test names** that explain what's being tested

## References

- [Testing Strategy](testing-strategy.md) - Overall testing approach
- ADR 028 - Pluggy+Dishka integration
- [Dishka Documentation](https://dishka.readthedocs.io/) - Dishka framework docs
- [Pytest Documentation](https://docs.pytest.org/) - Pytest testing framework
