# Lessons Learned: Dependency Injection

**Updated**: 2026-10-29, adding Dishka's coroutine-only `@inject` and one table for the repository registry. 2026-09-08, consolidated from the internal notes written while adopting Dishka (ADR 028, Pluggy + Dishka integration).

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

## Dishka's Litestar `@inject` only wraps coroutines

Migrating the dashboard controllers to `@inject` + `FromDishka` hit two constraints. The integration refuses sync functions, so the injected handlers are `async def` and hand their blocking work to `anyio.to_thread.run_sync` (see [`async-thread-boundaries.md`](./async-thread-boundaries.md)). And the provider's commit runs in its finalizer, after the response has been sent: a handler that writes and then redirects must commit inside its worker thread before returning, or the next page can read the old state. Check what an integration wraps before planning a migration around it.

## Read the finalizer contract before writing `except` around `yield`

The REQUEST-scoped session provider committed after `yield` and rolled back in an `except` around it. Dishka *sends* the handler's exception into the generator instead of throwing it, so the `except` branch never ran: a request whose handler failed was committed anyway. The scope no longer commits at all. Handlers commit inside their worker thread, and the finalizer rolls back and raises if writes are still pending when it closes, so a forgotten commit fails loud instead of being written after the response. Check how a library ends a generator before relying on `try`/`except` around its `yield`.

Under Litestar the scope's finalizer also runs after the response, and it never learns that the handler raised: Litestar turns the exception into a response first. So the outcome is decided by two app hooks, around the scope rather than inside it. `after_request` checks the request's session (kept in a context variable by the provider) for uncommitted writes and replaces the success with an error; `after_exception` rolls back. A check in the finalizer can only reach the log.

## One table builds the registry and its consumers

The RPC layer resolved repositories from its own `REPOSITORY_TYPES` table while `di/providers.py` declared them again, and the copies drifted (`port_claim_repo` was missing from the provider). The table now lives in `di/providers.py`, the provider is built from it, and the container test iterates the same table. When two places list the same things, build one from the other and test by iterating the source.

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

## The request scope lasts as long as the response

The dashboard's log stream looked the app up through a request-scoped `AppRepository` and returned a `Stream`. Dishka closes the request scope after the response is fully sent, and the SELECT had begun a transaction, so every open log tab held a pooled connection for as long as it stayed open: about fifteen tabs exhaust a pool of 5 plus 10 overflow and block every other request, login included. A handler that returns a long-lived response (SSE, a streamed download) ends its read transaction before returning. The provider also set the "current request session" context variable without resetting it, so a non-web caller that opened a REQUEST scope kept a closed session as its current one; keep the token from `set()` and reset it in a `finally`.

## Importing a module must not read the live configuration

Three scripts pointed `HOP3_ROOT` at a temporary directory before `import hop3`, because importing server modules read the live `hop3-server.toml`. The cause was `from hop3.config import config` in a dozen modules: the module `__getattr__` built the singleton at import. `config` is now a proxy that builds nothing until a setting is read, and the three workarounds are gone. A workaround copied into several callers points at one import-time side effect. Tests that patched `type(config)` broke when `config` became a proxy; patch the class by name.
