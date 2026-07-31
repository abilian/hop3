# ADR 038: Multi-Service Application Support

- **Status**: Accepted
- **Type**: Feature
- **Created**: 2026-04-11
- **Related-ADRs**: [008](./008-nix-builders-2.md) (Nix templates), [020](./020-pluggable-architecture.md) (pluggable architecture), [022](./022-build-deploy-plugin-system.md) (build/deploy plugins), [032](./032-deployment-strategies-artifact-lifecycle.md) (deployment strategies), [036](./036-cli-ergonomics.md) (CLI ergonomics)

## Context

Hop3's current deployment model assumes a single application = single logical process group. An app can have multiple *workers* via `[run.workers]` (e.g., `web`, `worker`, `scheduler`), but they all share the same source tree, the same environment, the same addons, and the same runtime. This fits a large class of 12-factor apps but breaks down for several real-world cases.

### Three patterns the single-process model handles poorly

**Pattern 1: Same-app background tasks.** The main app process runs the web server; a secondary process handles cron jobs, queue workers, or scheduled maintenance. Both share the source tree and the addon credentials. This is common in PHP/Laravel (queue workers), NextCloud (cron), and Rails (Sidekiq when the worker is configured simply).

**Pattern 2: Same-app multi-process with shared source, different commands.** Mastodon's Rails app, Sidekiq background workers, and Streaming API all run from the same source tree but with different commands and potentially different resource limits. They share the database and Redis addons.

**Pattern 3: Truly independent components.** AppFlowy Cloud has PostgreSQL + Redis + MinIO + GoTrue + background workers, each running different binaries, each with different configurations, but all making up one logical "application" from the user's perspective. The components are independently scalable and upgradeable.

### What `[run.workers]` already handles

The `[run.workers]` dict in `hop3.toml` already supports multiple named processes:

```toml
[run]
start = "gunicorn app:app"  # implicit "web" worker

[run.workers]
worker = "celery -A app worker --loglevel=info"
scheduler = "celery -A app beat --loglevel=info"
```

Each entry becomes a uWSGI daemon process in the same vassal config, sharing the source tree, env vars, addons, and working directory. This covers **Pattern 1** well and **Pattern 2** adequately for simple cases.

### What `[run.workers]` does NOT handle

1. **Per-process resource limits.** All workers share one memory limit. You can't say "Rails gets 2GB, Sidekiq gets 1GB".
2. **Per-process env overrides.** All workers see the same environment. You can't say "Sidekiq should have SIDEKIQ_CONCURRENCY=10 while Rails should not".
3. **Per-process scaling.** `hop3 ps scale` scales all workers of a given name; there's no "2 web + 4 sidekiq + 1 streaming" story.
4. **Truly independent components.** For AppFlowy-Cloud-class apps (Pattern 3), you can't declare that the app depends on PgBouncer as a separate process in its own isolation boundary.
5. **Per-component health checks.** One `[healthcheck]` per app.
6. **Process ordering dependencies.** "Start the database migrations before the web worker" is handled ad-hoc via `before-run`. There's no "start Sidekiq only after Rails is healthy" semantics.

### What other PaaS do

| System | Model | Notes |
|--------|-------|-------|
| Heroku Procfile | Flat list of process types (`web`, `worker`, ...) | Each type scales independently via dyno formation |
| Render `services.yaml` | One service per YAML entry; `type: web|worker|cron`; services share env groups | Each service has its own resource config |
| Fly.io `processes` | Flat list keyed by name, shared image | Each process gets its own VM in the fleet |
| K8s Pods | N containers per pod, sharing network namespace | Sidecar pattern |
| K8s Deployments | N pods of M containers each | Truly independent scaling |

Hop3's single-binary single-server constraint rules out the K8s answers. Heroku's flat model is closest to what we have; Render's shared-env-group approach is closest to what we need.

## Decision

We keep `[run.workers]` for Pattern 1 (shared-env background tasks) and introduce **`[[component]]` tables** for Pattern 2 and 3 (per-component config). A single `hop3.toml` can declare:

- Zero or more `[run.workers]` entries (flat, shared env)
- Zero or more `[[component]]` tables (per-component env, limits, health checks)
- At most one `[run]` section (the "primary" web component: stays for backward compatibility)

### When to use which

| Need | Use |
|------|-----|
| Simple cron worker, shares addons with web | `[run.workers.cron]` |
| Background queue, same env as web | `[run.workers.worker]` |
| Separate memory limit per process | `[[component]]` |
| Different health check per process | `[[component]]` |
| Independent scaling (2 web + 4 sidekiq) | `[[component]]` |
| Truly independent components (Mastodon, AppFlowy) | `[[component]]` |

The rule of thumb: **`[run.workers]` when the processes are variants of the main app; `[[component]]` when they have distinct lifecycles, configs, or resource needs.**

### `[[component]]` schema

```toml
[metadata]
id = "mastodon"

# Shared across all components
[[addons]]
type = "postgres"

[[addons]]
type = "redis"

# Primary web component: backward compatible with [run].start
[[component]]
name = "web"
command = "bundle exec puma -C config/puma.rb"
port = "web"  # exposes this component via the nginx front-end
scale = 2
memory-limit = "1G"

[component.env]
RAILS_ENV = "production"
WEB_CONCURRENCY = "2"

[component.healthcheck]
path = "/health"
interval = 30
timeout = 5

# Background queue
[[component]]
name = "sidekiq"
command = "bundle exec sidekiq"
scale = 4
memory-limit = "512M"
depends-on = ["web"]  # start order, not blocking

[component.env]
SIDEKIQ_CONCURRENCY = "10"

# Streaming API (different binary)
[[component]]
name = "streaming"
command = "node streaming/index.js"
port = "streaming"
memory-limit = "256M"
runtime = "node"  # optional: force a specific toolchain

[component.env]
NODE_ENV = "production"

# Port definitions: explicit for multi-component apps
[port.web]
container = 3000
public = true

[port.streaming]
container = 4000
public = true
```

### Env resolution order

For each component process, environment variables are layered in this order (later wins):

1. Component-specific runtime defaults (e.g., the toolchain's baseline)
2. Addon-injected vars (`DATABASE_URL`, `PGHOST`, `REDIS_URL`, ...)
3. Top-level `[env]` (shared across all components)
4. `[component.env]` (per-component overrides)
5. Admin overrides via `hop3 env set --app <app> KEY=val`

This matches how `[env]` already works but adds a component layer.

### Addon sharing

Addons declared at the top level (`[[addons]]`) are attached to **all** components. This is the common case: Mastodon's Postgres serves the web, sidekiq, and streaming processes equally.

For independent addons (rare), a component can declare its own:

```toml
[[component.addons]]
type = "redis"  # dedicated Redis for this component
```

Per-component addons are out of scope for this design; the supported model is top-level addons shared by all components.

### Lifecycle and dependencies

Components start in topological order based on `depends-on`. `depends-on` is a **start-ordering hint**: if dependent components fail to start, dependents still try.

`hop3 ps scale --app <app> web=2 sidekiq=4` scales individual components. Existing `[run.workers]` keeps current flat semantics.

Health checks run per-component. An app is "healthy" only if all non-optional components are healthy.

### Backward compatibility

The existing `[run]` + `[run.workers]` model is preserved. Apps using it continue to work unchanged. Internally, a legacy config is translated to a single implicit `[[component]]` at load time:

```toml
# Legacy
[run]
start = "gunicorn app:app"
[run.workers]
cron = "python manage.py cron"
```

Becomes (internally):

```toml
[[component]]
name = "web"
command = "gunicorn app:app"

[[component]]
name = "cron"
command = "python manage.py cron"
```

Existing addon, env, and port handling remain unchanged in the legacy path.

### What stays out of scope

- **Inter-component networking beyond shared-loopback.** Components share the app's working directory and 127.0.0.1. They don't get their own DNS entries inside the app's namespace. A component reaches another on its declared port.
- **Rolling restarts across components.** Covered by [ADR 032](./032-deployment-strategies-artifact-lifecycle.md), not re-opened here.
- **Per-component backups.** Backups are per-addon.
- **Sidecar containers.** Hop3 doesn't run containers for apps. Everything runs as uWSGI-managed processes under the hop3 user.
- **Full-fledged service mesh.** Hop3 is a single-server PaaS; the day we need a mesh is the day we've outgrown Hop3's model.
- **Multi-app composition**, where several independently-deployed apps form a logical whole, belongs in a separate ADR. This one is strictly intra-app.

## Consequences

### Positive

- Mastodon, AppFlowy, and similar multi-process apps become expressible in `hop3.toml` without `before-run` hacks.
- Per-component memory limits prevent one runaway process from taking down the rest.
- Per-component health checks give operators a real picture of which part of the app is failing.
- Independent scaling aligns with real production patterns.
- The ADR gives users and plugin authors a clear vocabulary: "component" for the unit of isolation, "worker" for the unit of flat scale.

### Negative

- **Two ways to declare processes** (`[run.workers]` vs `[[component]]`). We'll need crisp docs distinguishing them. Mitigation: the rule of thumb above, plus examples in the user guide. Both get translated to the same internal representation.
- **Schema complexity.** `hop3.toml` grows. Mitigation: keep the simple case (`[run].start`) unchanged: users only touch `[[component]]` when they need it.
- **Validation burden.** Per-component resource limits, health checks, and port mappings need validation. Mitigation: reuse the existing `Hop3TomlSchema` approach (Pydantic).
- **Runtime complexity.** spawn.py grows to handle per-component env layering and resource limits. Mitigation: the component layer is just a richer Worker description; the core spawn loop stays the same.

## Example: Mastodon

Mastodon's `hop3.toml` becomes:

```toml
[metadata]
id = "mastodon"
version = "4.3.0"
description = "Federated social network"

[build]
builder = "docker"  # or nix, when a template exists

[[addons]]
type = "postgres"

[[addons]]
type = "redis"

[[component]]
name = "web"
command = "bundle exec puma -C config/puma.rb"
port = "web"
scale = 2
memory-limit = "1G"

[component.healthcheck]
path = "/health"

[[component]]
name = "sidekiq"
command = "bundle exec sidekiq"
scale = 4
memory-limit = "768M"

[component.env]
SIDEKIQ_CONCURRENCY = "10"

[[component]]
name = "streaming"
command = "node streaming/index.js"
port = "streaming"
memory-limit = "256M"

[port.web]
container = 3000
public = true

[port.streaming]
container = 4000
public = true
```

This is the shape the plugin should emit and the shape the user (eventually) writes by hand.

## Open questions

1. **Port addressing syntax.** Should `port = "web"` refer to a named `[port.*]` entry, or should components declare their own port tables? Decision: named references into the top-level `[port.*]` dict, for consistency with the existing schema.
2. **What's the default `name` if `[[component]]` omits it?** A positional default (the component table index, e.g. `c0`) is error-prone, so `name` is required explicitly.
3. **Can a component declare its own builder/toolchain?** The `runtime = "node"` field above suggests yes. Decision: deferred: initially, all components share the app's build artifact.
4. **Cron-style scheduling.** Should `[component.schedule]` exist for cron-like components? Decision: keep the existing `cron` worker type for now.

## References

- `notes/experience-reports/00-aggregate.md` §Multi-Component Applications
- AppFlowy Cloud packaging attempt (internal report; surfaces the multi-component gap this ADR addresses)
- [ADR 022](./022-build-deploy-plugin-system.md): Build and Deployment Plugin System
- [ADR 032](./032-deployment-strategies-artifact-lifecycle.md): Deployment Strategies and Artifact Lifecycle
