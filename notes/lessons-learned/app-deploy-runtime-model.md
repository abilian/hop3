# App deploy & runtime model

How a Hop3 app behaves as it moves config → build → run, and how to read its
failures. These are platform lessons (originally harvested while building the
demos); none are demo-specific.

Related: [`uwsgi-daemon-management.md`](./uwsgi-daemon-management.md) (Emperor /
vassal / `attach-daemon` env propagation) and
[`deployment-diagnostics.md`](./deployment-diagnostics.md) (making failures
actionable).

---

## Each CLI command is an isolated RPC — never assume prior session state

Each CLI command is a separate RPC call with its own database session.
Relationships loaded (or appended) in one session are **not** carried into the
next call.

```python
# Call 1: env set --app myapp HOST_NAME=example.com
app.env_vars.append(EnvVar(...))   # added to session 1
session.commit()

# Call 2: deploy (a NEW session, NEW request)
app = repo.get(app_name)           # fresh load
app.env_vars                       # may be empty unless explicitly (re)loaded
```

**Do:** load relationships explicitly where they're needed, rather than relying
on state from a previous request.

```python
def get_runtime_env(self) -> dict:
    """Load env_vars explicitly — don't rely on prior session state."""
    return {ev.name: ev.value for ev in self.env_vars}
```

**Key insight:** in an RPC architecture, treat every request as completely
isolated. State from a prior command is not accessible unless re-fetched.

---

## App state-machine transitions: deploy ≠ redeploy

Valid transitions:

```
STOPPED → STARTING → RUNNING   (normal startup)
RUNNING → STOPPING → STOPPED   (normal shutdown)
any state → FAILED             (error)
```

Invalid transitions raise `StateTransitionError` — notably `RUNNING → RUNNING`
(redeploy without stopping) and `STOPPED → RUNNING` (skipping `STARTING`).

A deployer must handle **both** fresh deployment and redeployment, and the
pattern differs by whether there's a running process:

```python
# Stateful deployers (uWSGI): stop first, then start again.
if app.run_state == RUNNING:
    app.stop()

# Stateless deployers (static): no process to cycle — just update config.
if app.run_state == RUNNING:
    update_nginx_config()
    return
```

**Key insight:** redeploy is a distinct path from first-deploy; don't drive a
state transition that the deployer's runtime doesn't actually have.

---

## Build-time env ≠ runtime env — persist what runtime needs

Environment variables come from different sources at different stages:

- **Build time** (toolchain `get_env()`): `PATH` with virtualenv bins,
  language-specific vars (`BUNDLE_PATH`, `GEM_HOME`, `NODE_PATH`). Build tools
  need these to install dependencies.
- **Runtime** (spawn `make_env()`): base settings (`APP`, `HOME`, `PATH`,
  `VIRTUAL_ENV`), then the app's `ENV` file (committed with the code), then
  `env_vars` from the database (`env set`/`config set`), then safe defaults
  (`HOST_NAME=_`, `BIND_ADDRESS=127.0.0.1`).

Common mistake — setting a var at build time but not persisting it for runtime:

```python
# BAD — only present during the build
env["GEM_HOME"] = virtualenv_path

# GOOD — persist to the ENV file so it's there at runtime
(src_path / "ENV").open("a").write(f"GEM_HOME={virtualenv_path}\n")
```

**Key insight:** the build environment is not the runtime environment. A
toolchain must persist any variable the running process will need.

---

## 502 means connectivity, not a bad response

A `502 Bad Gateway` means nginx **cannot connect to the backend** — not that the
backend returned something invalid. Common causes:

1. App crashed on startup → read the logs.
2. Wrong port binding → check `$PORT` and the uWSGI/process config.
3. Missing runtime env vars → check the `ENV` file and the database.
4. Socket/port not ready yet → a timing issue (see retry, below).

```bash
hop3 app logs --app myapp      # crash messages
hop3 app status --app myapp    # is the state RUNNING?
hop3 app ping --app myapp      # is it actually answering?
```

**Key insight:** a 502 is a "backend isn't listening" problem — look at why the
process isn't up, not at what it's returning. (Hop3's deploy gate now probes
HTTP, not just a bound socket — see `deployment-diagnostics.md`.)

---

## PaaS deployments are eventually consistent — tests must retry

Apps don't start instantly; an HTTP check immediately after deploy can race the
process coming up. Poll instead of asserting once:

```python
for _ in range(10):
    resp = requests.get(url)
    if resp.status_code != 502:
        break
    time.sleep(2)   # give the app time to bind
assert resp.status_code == 200
```

**Key insight:** account for startup time in any test that hits a freshly
deployed app.

---

## HOST_NAME semantics: catch-all vs named vhost

- `HOST_NAME=_` → nginx catch-all, no specific hostname (development default).
- `HOST_NAME=example.com` → an nginx `server_name` vhost (production).

Proxy setup is **skipped** in catch-all mode:

```python
if not host_name or host_name == "_":
    log("Skipping proxy setup (catch-all mode)")
    return
```

**Key insight:** dev mode (no hostname) and production (named host) take
different proxy paths. A test that wants a real vhost must set `HOST_NAME`
explicitly (and redeploy) — the demos do this via `set_hostname()`.
