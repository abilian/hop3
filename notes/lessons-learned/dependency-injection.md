# Lessons Learned: Dependency Injection

**Updated**: 2026-09-08, consolidated from the internal notes written while adopting Dishka (ADR 028, Pluggy + Dishka integration).

This note covers when a class should be a DI-managed service, which scope it gets, and how to test it. The testing side is spelled out in [`docs/src/developers/di-testing-guide.md`](../../docs/src/developers/di-testing-guide.md).

## DI is for resources and lifecycles

A class belongs in the container when it manages a resource (a database session, a client, a socket), has a lifecycle (startup, shutdown, cleanup), needs configuration, or is a stateless singleton shared by many callers: `BackupManager`, `PostgresAdmin`, `RedisClientFactory`.

A class stays out of the container when it is built from data (`GitManager(app)`, a value object), is a plain utility, or is created per operation with specific inputs. If `MyClass(data)` reads better than injecting it, do not inject it; value objects in the container were the most common early mistake.

## Two scopes, chosen by what the service holds

- **APP** (one per container): stateless services and configuration-derived ones.
- **REQUEST** (one per request or operation): anything holding a database session or per-request state.

A database-backed service in APP scope shares one session across everything, the second most common mistake. Provide sessions as `Iterator[Session]` in REQUEST scope: commit, rollback and close become the provider's job, and no consumer can forget them:

```python
@provide(scope=Scope.REQUEST)
def get_session(self) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

REQUEST-scoped services are resolved inside a request container (`with di_container() as request: request.get(BackupManager)`), never from the app container directly. Dishka also resolves annotations at runtime; a type imported under `if TYPE_CHECKING:` is invisible to it, so provider signatures import their types for real.

## Plugins contribute providers through a hook

A plugin returns its providers from `get_di_providers()`; the container discovers them, and nothing registers them by hand. Litestar handlers take their services through `@inject` and `FromDishka[...]`.

## Test with real services and an in-memory database

Use the `di_container` fixture and let it build the real graph against SQLite in memory. A mocked session tests the mock. Fixtures own setup and teardown; a `try/finally` around a container in a test body means a fixture is missing, and so does touching `os.environ` outside one.

An in-memory SQLite database belongs to the connection that opened it. Litestar's `TestClient` serves the app on another thread, so a test that writes an account in memory and then calls the app over HTTP meets an empty database: the RPC authorization tests of September 2026 failed with `no such table: sec_user`. A test that crosses the HTTP boundary uses a file under `tmp_path` (the `file_db` fixture in `tests/b_integration/server/conftest.py`).

## Decision tree

```
Manages a resource or has a lifecycle?
├─ yes → DI
│   ├─ needs a database session → REQUEST scope
│   └─ stateless or configuration-derived → APP scope
└─ no → not DI
    ├─ built from data → construct it directly
    ├─ a utility → module functions
    └─ created per operation → a factory, not the container
```
