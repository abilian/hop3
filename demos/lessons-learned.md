# Lessons Learned from Demo Development

Architectural insights and reusable knowledge from building and debugging Hop3 demos.

## SQLAlchemy Session Management

### Lazy Loading Across RPC Boundaries

**Problem**: Each CLI command is a separate RPC call with its own database session. Relationships loaded in one session aren't available in subsequent calls.

```python
# Session 1: config:set HOST_NAME=example.com
app.env_vars.append(EnvVar(...))  # Added to session 1
session.commit()

# Session 2: deploy (NEW session)
app = repo.get(app_name)  # Fresh load
app.env_vars  # May be empty if not eagerly loaded!
```

**Solution**: Always explicitly load relationships when needed:
```python
def get_runtime_env(self) -> dict:
    """Load env_vars explicitly - don't rely on prior session state."""
    return {ev.name: ev.value for ev in self.env_vars}
```

**Key Insight**: In RPC architectures, treat each request as completely isolated. Never assume prior state is accessible.

---

## uWSGI Process Management

### Shell Variable Expansion in attach-daemon

**Problem**: uWSGI's `attach-daemon` directive uses `exec()` directly, not a shell. Environment variables like `$PORT` are not expanded.

```ini
# BAD - $PORT stays literal
attach-daemon = gunicorn --bind 0.0.0.0:$PORT app:app

# GOOD - shell expands $PORT
attach-daemon = sh -c "gunicorn --bind 0.0.0.0:$PORT app:app"
```

**Why**: `exec()` replaces the process without spawning a shell. Variable expansion is a shell feature.

**Key Insight**: When process managers use `exec()`, wrap commands in `sh -c "..."` for variable expansion.

---

## State Machine Transitions

### Valid App State Transitions

```
STOPPED → STARTING → RUNNING  (normal startup)
RUNNING → STOPPING → STOPPED  (normal shutdown)
Any state → FAILED            (error condition)
```

**Invalid transitions raise `StateTransitionError`**:
- RUNNING → RUNNING (redeployment without stop)
- STOPPED → RUNNING (skipping STARTING)

**Redeployment Pattern**:
```python
# For stateful deployers (uWSGI): stop first, then restart
if app.run_state == RUNNING:
    app.stop()

# For stateless deployers (static): skip state transition
if app.run_state == RUNNING:
    # Just update config, don't touch state
    update_nginx_config()
    return
```

**Key Insight**: Deployers must handle both fresh deployment and redeployment. The patterns differ based on whether there's a running process.

---

## Environment Variable Flow

### Build Time vs Runtime

Environment variables have different sources at different stages:

**Build Time** (toolchain's `get_env()`):
- PATH with virtualenv bins
- Language-specific vars (BUNDLE_PATH, GEM_HOME, NODE_PATH)
- Build tools need these to install dependencies

**Runtime** (spawn's `make_env()`):
1. Base settings (APP, HOME, PATH, VIRTUAL_ENV)
2. ENV file from app's src directory (committed with code)
3. env_vars from database (set via `config:set`)
4. Safe defaults (HOST_NAME=_, BIND_ADDRESS=127.0.0.1)

**Common Mistake**: Setting env vars at build time but not persisting them for runtime.

```python
# BAD - only available during build
env["GEM_HOME"] = virtualenv_path

# GOOD - persist to ENV file for runtime
env_file = src_path / "ENV"
with open(env_file, "a") as f:
    f.write(f"GEM_HOME={virtualenv_path}\n")
```

**Key Insight**: Build environment ≠ runtime environment. Toolchains must persist any vars needed at runtime.

---

## Debugging HTTP Errors

### 502 Bad Gateway

**Means**: Reverse proxy (nginx) cannot connect to the backend.

**NOT**: Backend returned invalid response (that's 502 from upstream, different cause).

**Common Causes**:
1. App crashed on startup → check `hop3 app:logs`
2. Wrong port binding → verify PORT env var and uWSGI config
3. Missing runtime env vars → check ENV file and database
4. Socket/port not ready → timing issue, add retry logic

**Debugging Flow**:
```bash
hop3 app:logs myapp        # See crash messages
hop3 app:status myapp      # Verify state is RUNNING
hop3 app:ping myapp        # Check if responding
```

**Key Insight**: 502 = connectivity problem. Look at why backend isn't listening, not at what it's returning.

---

## Testing Async Services

### Retry Logic for Eventually-Consistent Systems

Apps don't start instantly. HTTP tests need retry logic:

```python
def test_app_responds():
    for attempt in range(10):
        response = requests.get(url)
        if response.status_code != 502:
            break
        time.sleep(2)  # Give app time to start

    assert response.status_code == 200
```

**Key Insight**: PaaS deployments are eventually consistent. Tests must account for startup time.

---

## Proxy Configuration

### HOST_NAME Semantics

- `HOST_NAME=_` → nginx catch-all, no specific hostname (development)
- `HOST_NAME=example.com` → nginx server_name directive (production)

**Proxy setup is skipped when HOST_NAME is "_"**:
```python
if not host_name or host_name == "_":
    log("Skipping proxy setup (catch-all mode)")
    return
```

**Key Insight**: Development mode (no hostname) and production mode (with hostname) have different proxy behaviors. Tests should set HOST_NAME explicitly.
