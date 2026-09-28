# App deploy & runtime model

This file describes how a Hop3 app behaves as it moves through config → build → run, and how to read its failures. These are platform lessons (originally harvested while building the demos); none are demo-specific.

See also [`uwsgi-daemon-management.md`](./uwsgi-daemon-management.md) (Emperor / vassal / `attach-daemon` env propagation) and [`deployment-diagnostics.md`](./deployment-diagnostics.md) (making failures actionable).

---

## Each CLI command is an isolated RPC: never assume prior session state

Each CLI command is a separate RPC call with its own database session. Relationships loaded (or appended) in one session are **not** carried into the next call.

```python
# Call 1: env set --app myapp HOST_NAME=example.com
app.env_vars.append(EnvVar(...))   # added to session 1
session.commit()

# Call 2: deploy (a NEW session, NEW request)
app = repo.get(app_name)           # fresh load
app.env_vars                       # may be empty unless explicitly (re)loaded
```

**Do:** load relationships explicitly where they're needed. State from a previous request is gone.

```python
def get_runtime_env(self) -> dict:
    """Load env_vars explicitly - don't rely on prior session state."""
    return {ev.name: ev.value for ev in self.env_vars}
```

---

## App state-machine transitions: deploy ≠ redeploy

Valid transitions:

```
STOPPED → STARTING → RUNNING   (normal startup)
RUNNING → STOPPING → STOPPED   (normal shutdown)
any state → FAILED             (error)
```

Invalid transitions raise `StateTransitionError`, notably `RUNNING → RUNNING` (redeploy without stopping) and `STOPPED → RUNNING` (skipping `STARTING`).

A deployer must handle **both** fresh deployment and redeployment, and the pattern differs by whether there's a running process:

```python
# Stateful deployers (uWSGI): stop first, then start again.
if app.run_state == RUNNING:
    app.stop()

# Stateless deployers (static): no process to cycle - just update config.
if app.run_state == RUNNING:
    update_nginx_config()
    return
```

Redeploy is its own path. Drive only the transitions the deployer's runtime has.

---

## Build-time env ≠ runtime env: persist what runtime needs

Environment variables come from different sources at different stages:

- **Build time** (toolchain `get_env()`): `PATH` with virtualenv bins, language-specific vars (`BUNDLE_PATH`, `GEM_HOME`, `NODE_PATH`). Build tools need these to install dependencies.
- **Runtime** (spawn `make_env()`): base settings (`APP`, `HOME`, `PATH`, `VIRTUAL_ENV`), then the app's `ENV` file (committed with the code), then `env_vars` from the database (`env set`/`config set`), then safe defaults (`HOST_NAME=_`, `BIND_ADDRESS=127.0.0.1`).

The common mistake is to set a var at build time and never persist it for runtime:

```python
# BAD - only present during the build
env["GEM_HOME"] = virtualenv_path

# GOOD - persist to the ENV file so it's there at runtime
(src_path / "ENV").open("a").write(f"GEM_HOME={virtualenv_path}\n")
```

The `ENV` file is the pre-artifact mechanism. Toolchains now write what the running process needs into the build artifact; see "The build artifact is the runtime contract" below.

---

## 502 means the backend is unreachable

A `502 Bad Gateway` means nginx **cannot connect to the backend**. Common causes:

1. App crashed on startup → read the logs.
2. Wrong port binding → check `$PORT` and the uWSGI/process config.
3. Missing runtime env vars → check the `ENV` file and the database.
4. Socket/port not ready yet → a timing issue (see retry, below).

```bash
hop3 app logs --app myapp      # crash messages
hop3 app status --app myapp    # is the state RUNNING?
hop3 app ping --app myapp      # is it actually answering?
```

Check whether the process is up before examining its responses. Hop3's deploy gate now probes at the HTTP level; see [`deployment-diagnostics.md`](./deployment-diagnostics.md).

---

## PaaS deployments are eventually consistent: tests must retry

Apps don't start instantly, so an HTTP check immediately after deploy can race the process coming up. Poll:

```python
for _ in range(10):
    resp = requests.get(url)
    if resp.status_code != 502:
        break
    time.sleep(2)   # give the app time to bind
assert resp.status_code == 200
```

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

A test that wants a real vhost must set `HOST_NAME` explicitly and redeploy. The demos do this via `set_hostname()`.

---

## Port listening is the truth; database state waits for real state

`pgrep` finding a uWSGI process said nothing about whether the app had bound its port, and deploys were reported successful for apps that had crashed after starting. The gate is the port: set the row to RUNNING only after the port answers. The same discipline applies to stopping: the database said STOPPED while the process was still exiting, and the next deploy tripped over it. A state transition waits for the actual state (`wait_for_actual_state`) before anything depends on it. (Hop3's deploy gate has since moved up the ladder to HTTP and content checks; see [`verifying-an-app-works.md`](./verifying-an-app-works.md).)

---

## The build artifact is the runtime contract

`spawn.py` once detected the language at runtime, checking for `node_modules/` or a `Gemfile` and setting `NODE_PATH` or `GEM_HOME` by hand. That put language knowledge in core code, could not be extended without editing it, and could not describe an artifact built on one machine and run on another. The toolchain knows what runtime environment it produced; it writes `RuntimeConfig` (env vars, `PATH` entries, workers, working directory) into `BUILD_ARTIFACT.json` at build time, and the run phase applies it (ADR 030, ADR 035). The runtime detection remains only as the fallback for pre-artifact apps.

Two later lessons follow from the same contract:

- **One environment core.** `hop3 run` built its own environment from scratch and never read the artifact, so a Nix app's store binaries were not on its `PATH`. The workers' `make_env`, `hop3 run` and `hop3 app shell` now share one `build_app_env` (bootstrap, artifact env and `PATH`, then the persisted `[env]` under toolchain-wins precedence); a worker adds only what a worker needs.
- **Gate on the builder.** The Nix closure guard ran only for artifacts of `kind == "nix"`. The Nix builder emits a `static` artifact for a site the proxy serves straight from the store, so the guard returned before looking. A restart against a deleted closure succeeded: the scenario the guard was written for. The artifact's `builder` field is the fact; its `location` is a root of the closure whether or not a worker's command line mentions it.

---

## Build hooks are not workers

Build hooks and workers are different things. `before-build` commands were also registered as a `prebuild` worker, so `rm -rf _build deps && mix compile` ran as a daemon, forever, deleting the artifacts the web worker was using. The first deploy worked; the redeploy broke, with the Emperor logging a respawn loop.

| Kind | Runs | Owner |
|---|---|---|
| Build hooks (`before-build`, `post-build`) | once, during the deploy | the deployer's hook runner |
| Workers (`web`, `worker`, …) | continuously | uWSGI |

A `Procfile` entry is not a worker declaration either; toolchains declare their process model into the artifact. Mix also keeps dependency metadata that `rm -rf deps` leaves behind, so an Elixir clean build needs `mix deps.clean --all` before `mix deps.get`.

---

## A shell into the app: exec the spec, build the environment from scratch

`hop3 app shell` (September 2026) is `hop3 run` with a terminal. Three decisions made it safe to ship after a deleted first attempt. The session spec (`argv`, `cwd`, `env`) is a pure function of the app and its artifact, with no I/O. The environment comes from the same `build_app_env` as everything else, so the server's own `HOP3_SECRET_KEY`, database URL and the forced command's `FINGERPRINT` never reach the child. The process is replaced by `execve`, so the shell's exit status is the session's and there is no timeout to trip over. The transport is `ssh -t`, and sshd owns the pty, resizes and keepalives. bash starts with `--norc` so the `hop3` account's rc files cannot rewrite the toolchain's `PATH`, and `HISTFILE` is empty so an operator's keystrokes do not land in a shared history. The command changes duration and observability and grants no authority; see [`privilege-and-isolation.md`](./privilege-and-isolation.md).
