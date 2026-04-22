# ADR 023: Runtime Stack Replacement

**Status**: Draft (nothing implemented; no commitment to execute)
**Type**: Feature
**Created**: 2024-11-01
**Updated**: 2026-04-22
**Related-ADRs**: 021, 036

## Revisions

- v1.2: CLI example migrated from colon syntax (`hop3 app:deploy`) to space form (`hop3 deploy`) per ADR 036 (2026-04-22).
- v1.1: Explicit status note. The proposed replacement (Granian + Caddy + custom Python process manager, replacing uWSGI + nginx + supervisor) has **not** been started. The current runtime is the uWSGI emperor + nginx + optional supervisord fallback described throughout the other ADRs, and this is what 100+ app variants run on. This ADR captures a future direction that is not currently scheduled against any release (2026-04-14).
- v1.0: Original draft (2024-11-01)

## Current Status (2026-04-14)

Nothing from this ADR has been implemented. The motivation — uWSGI's development has ceased; hot reconfiguration; reduced complexity — remains valid, but the project has invested in other areas (Nix integration, test-suite diagnostics, app packaging) rather than a runtime-stack replacement. In the meantime the operational pain from uWSGI has been low enough that the replacement has not crossed the priority threshold.

**What still holds from the original motivation:**

- uWSGI's unmaintained status has not produced concrete incidents since this ADR was drafted, but remains a latent risk.
- Hot reconfiguration is still not provided by the current stack. `hop3 deploy` writes configs and reloads Nginx; there is no atomic-swap pathway.
- The three-component coupling (uWSGI vassal → Nginx site → optional supervisord) has been refined rather than simplified (see W16's systemd-vs-supervisord detection rework).

**What would need to happen to revive this ADR:**

1. Concrete incident or security advisory against uWSGI, OR
2. A hot-reconfiguration requirement from a real operator, OR
3. A strategic decision to align the runtime with the Nix-based build path (a Nix-packaged Granian + Caddy is closer in spirit to a Nix-first PaaS than the current C-heavy uWSGI).

Until one of those triggers, this ADR stays as a well-worked-out option on the shelf rather than an active workstream. The design below is retained for that future decision.

## Introduction

This ADR proposes replacing Hop3's current runtime stack (uWSGI + nginx + supervisor) with a modernized, simplified architecture that maintains all functionality while reducing complexity and improving maintainability. The goal is to achieve hot reconfiguration capabilities, eliminate unmaintained dependencies, and provide a cleaner separation of concerns.

## Summary

We propose replacing the current three-component stack (uWSGI for application serving, nginx for reverse proxy, supervisor for process management) with a streamlined architecture consisting of:

1. **Granian** - Modern Rust-based ASGI/WSGI server (replacing uWSGI)
2. **Caddy** - Modern reverse proxy with automatic HTTPS (replacing nginx)
3. **Custom Process Manager** - Lightweight Python daemon (replacing supervisor)

This new stack will provide hot reconfiguration (add/remove apps without restarts), automatic HTTPS via ACME, and eliminate dependency on unmaintained projects (uWSGI development has ceased).

## Context and Goals

### Context

Hop3 currently relies on three major components for its runtime:

1. **uWSGI** - Application server
   - Complex C codebase (10x more features than needed)
   - Development has ceased (no longer actively maintained)
   - Emperor mode provides hot reload capability
   - Supports multiple protocols (WSGI, RWSGI, JWSGI)

2. **nginx** - Reverse proxy
   - Battle-tested and reliable
   - Requires reload for configuration changes
   - Static configuration files
   - Hop3 generates configs via Python templates

3. **Supervisor** - Process manager (in test/dev environments)
   - Manages multiple processes
   - Limited hot reconfiguration
   - Requires `supervisorctl` commands for changes

This stack works but has significant drawbacks:
- **uWSGI is unmaintained** - Security and compatibility risks
- **No hot reconfiguration** - Adding apps requires nginx reloads
- **Complexity** - uWSGI has 100+ features, we use ~7
- **Tight coupling** - Components are interdependent

### Goals

1. **Eliminate unmaintained dependencies** - Replace uWSGI with actively maintained alternatives
2. **Enable hot reconfiguration** - Add/remove apps, update SSL, change routing without any restarts
3. **Reduce complexity** - Use simpler components that do one thing well
4. **Maintain functionality** - Support all current features (WSGI, Node.js, Ruby, SSL, virtual hosts, etc.)
5. **Improve developer experience** - Simpler architecture = easier to understand and debug
6. **Automatic HTTPS** - Built-in ACME/Let's Encrypt support without external tools

## Tenets

- **Simplicity over features** - Use components that provide exactly what we need, no more
- **Modern, maintained software** - Actively developed projects with strong communities
- **Hot reconfiguration everywhere** - No restarts required for routine operations
- **Clear separation of concerns** - Each component has one job
- **Convention over configuration** - Smart defaults with explicit overrides when needed

## Decision

We will replace the current runtime stack with:

**Option 1: Caddy + Custom Process Manager + Granian** (Recommended)

Components:
1. **Granian** - Rust-based ASGI/WSGI server (app execution layer)
2. **Caddy** - Reverse proxy with automatic HTTPS (edge layer)
3. **Custom Process Manager** - Python daemon for lifecycle management (control layer)

Architecture:
```
┌─────────────────────────────────────────┐
│ Caddy (Reverse Proxy + SSL)             │
│ - Automatic HTTPS (ACME)                │
│ - Hot reload via JSON API               │
│ - Virtual host routing                  │
└────────────┬────────────────────────────┘
             │ Unix sockets
             ↓
┌─────────────────────────────────────────┐
│ Hop3 Process Manager (Python daemon)    │
│ - Spawns/monitors Granian processes     │
│ - Health checks & auto-restart          │
│ - Lifecycle API (start/stop/reload)     │
└────────────┬────────────────────────────┘
             │
             ↓
┌─────────────────────────────────────────┐
│ Granian Processes (one per app)         │
│ - Runs application code (WSGI/ASGI)     │
│ - Unix socket per app                   │
│ - Process-per-app isolation             │
└─────────────────────────────────────────┘
```

**Alternative Option 2: All-Python Stack**

Components:
1. **Hypercorn/Uvicorn** - Python ASGI server (replaces both nginx and Granian)
2. **Custom Reverse Proxy** - Python ASGI middleware (routing layer)
3. **acme library** - Python ACME client (SSL/TLS)
4. **Same Custom Process Manager** - Python daemon

## Detailed Design

### Component Selection Rationale

#### Granian (replacing uWSGI)

**Why Granian?**
- ✅ Rust-based - Fast, memory-safe, actively maintained
- ✅ Already a dependency - hop3-server uses it
- ✅ ASGI/WSGI support - Handles Python apps
- ✅ Hot reload - Process-level reload support
- ✅ Unix sockets - Native support for nginx-style deployment
- ✅ ~5% complexity of uWSGI - Does what we need, nothing more

**Granian features we'll use:**
- WSGI/ASGI interface
- Unix socket communication
- Multi-worker support
- Threading support
- Process management
- Environment variables

**What we lose from uWSGI:**
- Ruby (RWSGI), Java (JWSGI) plugins → Can proxy to standalone Ruby/Java processes
- Emperor mode → Replaced by custom process manager
- Built-in cron → Use system cron or scheduled tasks
- Complex routing → Don't need it

#### Caddy (replacing nginx)

**Why Caddy?**
- ✅ Automatic HTTPS - Built-in ACME, zero configuration
- ✅ Hot reload via API - JSON API for config changes without restart
- ✅ Single binary - Easy to install and update
- ✅ Modern protocols - HTTP/2, HTTP/3, WebSocket support
- ✅ Battle-tested - Production-grade, widely deployed
- ✅ Simple configuration - JSON or Caddyfile

**Caddy API example:**
```bash
# Add new app instantly (no restart)
curl -X POST http://localhost:2019/config/ \
  -H "Content-Type: application/json" \
  -d '{
    "apps": {
      "http": {
        "servers": {
          "hop3": {
            "routes": [{
              "match": [{"host": ["newapp.example.com"]}],
              "handle": [{
                "handler": "reverse_proxy",
                "upstreams": [{"dial": "unix//home/hop3/sockets/newapp.sock"}]
              }]
            }]
          }
        }
      }
    }
  }'
```

**What we lose from nginx:**
- Extensive tuning options → Caddy has sensible defaults
- nginx-specific modules → Don't use any Hop3-specific ones
- Familiarity → Learning curve for Caddy

#### Custom Process Manager (replacing supervisor)

**Why custom?**
- ✅ Hop3-specific - Exactly our needs, no more
- ✅ Tight integration - Direct API with hop3-server
- ✅ Hot reconfiguration - Full control over lifecycle
- ✅ Simple implementation - ~300-500 lines of Python
- ✅ asyncio-based - Modern Python patterns

**Core features:**
```python
class ProcessManager:
    async def start_app(self, app_name: str, **config):
        """Start Granian for an app."""

    async def stop_app(self, app_name: str, timeout: int = 30):
        """Gracefully stop an app."""

    async def reload_app(self, app_name: str):
        """Zero-downtime reload."""

    async def scale_app(self, app_name: str, workers: int):
        """Scale workers."""

    async def get_status(self, app_name: str) -> dict:
        """Get app health status."""
```

**What we lose from supervisor:**
- GUI (supervisorctl web interface) → Use hop3 CLI/API
- Generic process management → Hop3-specific instead

### Implementation Architecture

```
packages/hop3-server/src/hop3/
├── run/
│   ├── pm/                    # New: Process Manager
│   │   ├── __init__.py
│   │   ├── manager.py         # ProcessManager class
│   │   ├── process.py         # AppProcess wrapper
│   │   └── monitor.py         # Health monitoring
│   └── spawn.py               # Updated: Use Granian instead of uWSGI
├── proxy/
│   ├── caddy/                 # New: Caddy integration
│   │   ├── __init__.py
│   │   ├── api.py             # Caddy JSON API client
│   │   ├── config.py          # Config generation
│   │   └── acme.py            # ACME setup
│   └── nginx/                 # Deprecated: Keep for migration
└── plugins/
    └── deploy/
        ├── granian/           # New: Granian deployer
        │   ├── deployer.py
        │   └── plugin.py
        └── uwsgi/             # Deprecated: Keep for migration
```

### Deployment Workflow

**Current (uWSGI + nginx):**
```
1. Deploy app
2. Generate .ini files → /home/hop3/uwsgi-enabled/
3. Emperor detects new files, spawns workers
4. Generate nginx config → /home/hop3/nginx/app.conf
5. Reload nginx (supervisorctl restart nginx)
6. App is live
```

**Proposed (Granian + Caddy):**
```
1. Deploy app
2. ProcessManager.start_app()
   - Spawn Granian on unix socket
   - Monitor health
3. CaddyAPI.add_route()
   - Hot add route via JSON API
   - Caddy obtains SSL cert automatically
   - No restart
4. App is live
```

### Migration Strategy

**Phase 1: Parallel Implementation (2 weeks)**
- Implement ProcessManager
- Implement Caddy integration
- Add Granian deployer plugin
- Keep existing uWSGI/nginx code

**Phase 2: Feature Parity (1 week)**
- Test all app types (Python, Node.js, Ruby, etc.)
- Verify SSL/ACME functionality
- Performance testing
- Documentation

**Phase 3: Migration (1 week)**
- Update installer to include Caddy
- Default to new stack for new installs
- Provide migration script for existing deployments
- Update all documentation

**Phase 4: Deprecation (future)**
- Mark uWSGI/nginx code as deprecated
- Remove in next major version

## Examples and Interactions

### Example 1: Deploy a Python Flask App

**With new stack:**
```python
# User runs: hop3 deploy myapp

# 1. Build (unchanged)
builder = PythonBuilder(context)
artifact = builder.build()  # Creates venv

# 2. Deploy
deployer = GranianDeployer(context, artifact)
deployment_info = deployer.deploy()
# → ProcessManager spawns Granian on unix:/home/hop3/sockets/myapp.sock

# 3. Proxy
caddy_proxy = CaddyProxy()
caddy_proxy.configure(deployment_info)
# → Caddy API: add route for myapp.example.com → unix socket
# → Caddy obtains Let's Encrypt cert automatically

# Done! App is live with HTTPS
```

### Example 2: Scale Workers

```python
# User runs: hop3 scale myapp web=4

# ProcessManager
await pm.scale_app("myapp", workers=4)
# → Graceful reload with new worker count
# → No downtime
# → Caddy continues routing during reload
```

### Example 3: Add New App (Hot Reconfiguration)

```python
# User runs: hop3 deploy newapp

# No restarts anywhere!
# 1. ProcessManager starts new Granian
# 2. Caddy API adds route
# 3. ACME obtains SSL cert
# 4. Done - both apps running simultaneously
```

### Example 4: Non-Python App (Node.js)

```python
# For non-WSGI apps, ProcessManager runs them directly
await pm.start_app(
    app_name="nodeapp",
    command=["node", "server.js"],
    socket_path="/home/hop3/sockets/nodeapp.sock",
    env={"PORT": "8000"}
)

# Caddy proxies to the socket (app must listen on unix socket)
# Or use HTTP if app doesn't support sockets
```

## Consequences

### Benefits

1. **Simplified Stack**
   - 3 components with clear roles (vs. 3+ complex components)
   - Granian: ~1000 LOC Rust (vs. uWSGI: ~100k LOC C)
   - Custom PM: ~500 LOC Python (vs. supervisor: ~20k LOC)

2. **Hot Reconfiguration**
   - Add apps: instant (Caddy API + PM start)
   - Remove apps: instant (PM stop + Caddy API)
   - Update SSL: automatic (Caddy ACME)
   - Scale workers: graceful reload (PM)
   - **Zero downtime for routine operations**

3. **Automatic HTTPS**
   - Caddy handles ACME challenges
   - Auto-renewal
   - No certbot, no custom scripts
   - Works out of the box

4. **Modern, Maintained**
   - Granian: Active Rust project
   - Caddy: Active Go project
   - Both have strong communities

5. **Better Developer Experience**
   - Simpler to understand (less code, clearer roles)
   - Easier to debug (fewer layers)
   - Better error messages
   - API-driven configuration

6. **Performance**
   - Granian is Rust (faster than uWSGI Python plugin)
   - Caddy is Go (comparable to nginx)
   - Lower memory usage (no emperor overhead)

### Drawbacks

1. **New Dependencies**
   - Caddy binary must be installed
   - Learning curve for team
   - Different configuration paradigm

2. **Migration Effort**
   - ~4-6 weeks total implementation + testing
   - Existing deployments need migration
   - Documentation updates
   - Training/onboarding

3. **Less Proven (for Hop3)**
   - uWSGI + nginx is battle-tested in Hop3
   - New stack needs validation
   - Potential unknown issues

4. **Plugin Ecosystem**
   - uWSGI has Ruby/Java plugins
   - Granian is Python-focused
   - Workaround: Run Ruby/Node/etc. processes directly

5. **Operational Changes**
   - Different debugging approaches
   - Different monitoring/logging
   - New failure modes to learn

6. **All-in on Caddy**
   - If Caddy has issues, affects all apps
   - nginx is extremely stable
   - Caddy is newer (though mature)

## Lessons Learned

From previous experience with uWSGI:
- Emperor mode's hot reload is the "killer feature" - must replicate
- Simple config files (touch to reload) worked well - keep this pattern
- Most uWSGI features are unused - validate minimal feature set
- Process isolation is important - maintain one-process-per-app

From nginx experience:
- Static config files + reload is acceptable but suboptimal
- Virtual host routing is essential
- Unix sockets work better than TCP for local communication
- SSL automation is critical (certbot was complex)

## Action Items

### Research & Validation
- [ ] Benchmark Granian vs uWSGI for Python apps
- [ ] Validate Caddy hot reload performance
- [ ] Test Caddy ACME with Let's Encrypt staging
- [ ] Prototype ProcessManager core functionality

### Implementation
- [ ] Implement ProcessManager (~500 LOC)
- [ ] Implement Caddy API client (~300 LOC)
- [ ] Create GranianDeployer plugin
- [ ] Update spawn.py to support Granian
- [ ] Write integration tests

### Testing & Documentation
- [ ] Test all app types (Python, Node, Ruby, static)
- [ ] Performance benchmarks
- [ ] Load testing with multiple apps
- [ ] Migration guide for existing deployments
- [ ] Update all documentation

### Deployment
- [ ] Update installer to include Caddy
- [ ] Create migration script
- [ ] Deploy to test server
- [ ] User acceptance testing

### Rollout
- [ ] Release beta version
- [ ] Gather feedback
- [ ] Fix issues
- [ ] Release stable version
- [ ] Deprecate old stack

## Alternatives

### Alternative 1: Keep Current Stack + Patch uWSGI

**Description:** Continue using uWSGI + nginx, potentially forking uWSGI if critical bugs arise.

**Pros:**
- Zero migration effort
- Known quantity
- Existing documentation

**Cons:**
- uWSGI is unmaintained (security risk)
- No hot reconfiguration
- Technical debt accumulates

**Verdict:** Rejected - kicks the can down the road, doesn't solve core issues.

### Alternative 2: Traefik Instead of Caddy

**Description:** Use Traefik for reverse proxy instead of Caddy.

**Pros:**
- Service discovery built-in
- More enterprise features
- Metrics/observability

**Cons:**
- More complex than Caddy
- Heavier resource usage
- More verbose configuration

**Verdict:** Viable alternative, but Caddy's simplicity aligns better with Hop3's philosophy.

### Alternative 3: All-Python Stack (Hypercorn + Custom Proxy)

**Description:** Build everything in Python - reverse proxy, SSL management, process management.

**Pros:**
- No external dependencies
- Full control
- Tight integration

**Cons:**
- ~2000+ LOC to implement properly
- ACME is complex
- Proxy performance < Caddy
- Reinventing the wheel

**Verdict:** Interesting for learning but not practical - too much effort for marginal benefit.

### Alternative 4: systemd Only (No supervisor/PM)

**Description:** Use systemd templates for process management instead of custom PM.

**Pros:**
- Standard Linux approach
- Battle-tested
- No custom code

**Cons:**
- Linux-only (not macOS/BSD)
- Less flexible than programmatic API
- Harder to integrate with hop3-server

**Verdict:** Good for production, but custom PM provides better development experience and cross-platform support.

### Alternative 5: Keep nginx, Replace Only uWSGI

**Description:** Minimal change - just replace uWSGI with Granian, keep nginx.

**Pros:**
- Smaller migration
- Keep proven nginx
- Lower risk

**Cons:**
- No hot reconfiguration
- No automatic HTTPS
- Doesn't solve all problems

**Verdict:** Possible incremental approach, but doesn't achieve goal of hot reconfiguration.

## Prior Art

### Heroku
- Uses nginx + custom routing layer
- Dynamic routing without restarts
- Automatic SSL

### Fly.io
- Uses Caddy-like approach
- Hot configuration updates
- Built-in SSL

### Railway
- Uses Caddy
- Automatic HTTPS
- Simple deployment model

### Dokku
- Uses nginx + custom scripts
- Process management via systemd
- Static configuration (requires reload)

### CapRover
- Uses nginx + Docker
- Let's Encrypt integration
- Web UI for management

**Common patterns:**
- Modern PaaS platforms use hot reconfiguration
- Automatic SSL is table stakes
- Simplicity over features
- API-driven configuration

## Unresolved Questions

1. **Caddy License**
   - Apache 2.0 - compatible with Hop3's license ✓

2. **Granian Maturity**
   - How stable is Granian for production?
   - Need to validate with load testing

3. **Migration Path**
   - How to migrate existing deployments without downtime?
   - Can we run old and new stack simultaneously?

4. **Performance**
   - Will Granian match uWSGI performance?
   - Need benchmarks

5. **Non-Python Apps**
   - How to handle Ruby/Node.js/Go apps elegantly?
   - Proxy to standalone processes? Direct execution?

6. **Monitoring**
   - How to expose process manager metrics?
   - Integration with existing monitoring tools?

## Future Work

1. **Advanced Features**
   - Load balancing across multiple Granian instances
   - Blue-green deployments
   - Canary deployments
   - A/B testing support

2. **Observability**
   - Metrics collection from ProcessManager
   - Distributed tracing
   - Centralized logging

3. **High Availability**
   - Multi-server deployments
   - Shared state management
   - Failover mechanisms

4. **Developer Experience**
   - Local development mode without Caddy
   - Better error messages
   - Interactive debugging tools

5. **Ecosystem**
   - Alternative process managers (systemd plugin?)
   - Alternative proxies (Traefik plugin?)
   - Monitoring integrations

## Related

- **ADR-020: Pluggable Architecture** - This proposal fits within the plugin architecture, with Granian and Caddy as new plugins
- **ADR-010: Security and Resilience** - ACME integration improves security posture
- **ADR-002: Config Format** - hop3.toml can specify runtime preferences

## References

- [Granian Documentation](https://github.com/emmett-framework/granian)
- [Caddy Documentation](https://caddyserver.com/docs/)
- [Caddy JSON Config API](https://caddyserver.com/docs/api)
- [uWSGI Emperor Mode](https://uwsgi-docs.readthedocs.io/en/latest/Emperor.html)
- [ACME Protocol (RFC 8555)](https://tools.ietf.org/html/rfc8555)
- [Let's Encrypt Documentation](https://letsencrypt.org/docs/)

## Notes

- This ADR is marked as "Proposed" pending team discussion and approval
- Performance benchmarks should be conducted before final decision
- Migration strategy needs refinement based on deployment patterns
- Consider phased rollout: new installations first, then migrations

## Appendix

### A. Current uWSGI Features Actually Used

From analysis of `hop3/run/uwsgi/worker.py`:

**Core features:**
- Master process
- Process management (workers, threads)
- Environment variables
- Virtualenv support
- Unix sockets
- Logging with rotation
- Idle timeout

**Worker types:**
- WSGI (Python) - plugin=python3
- RWSGI (Ruby) - plugin=rack
- JWSGI (Java) - plugin=jvm
- Web (attach-daemon) - generic processes
- Cron - scheduled tasks

**NOT used:**
- Static file serving (nginx does this)
- Caching (nginx does this)
- Load balancing
- Clustering
- Legion subsystem
- Advanced routing
- ~90+ other features

### B. ProcessManager Prototype

```python
import asyncio
import signal
from pathlib import Path
from dataclasses import dataclass

@dataclass
class AppProcess:
    process: asyncio.subprocess.Process
    app_name: str
    socket_path: Path
    workers: int

class ProcessManager:
    def __init__(self):
        self.processes: dict[str, AppProcess] = {}
        self._running = False

    async def start(self):
        """Start the process manager daemon."""
        self._running = True
        asyncio.create_task(self._monitor_loop())

    async def start_app(
        self,
        app_name: str,
        wsgi_module: str,
        workers: int = 4,
        threads: int = 4,
        cwd: Path = None,
        env: dict = None,
    ):
        """Start Granian for an app."""
        socket_path = Path(f"/home/hop3/sockets/{app_name}.sock")
        socket_path.parent.mkdir(parents=True, exist_ok=True)
        socket_path.unlink(missing_ok=True)

        cmd = [
            "granian",
            "--interface", "wsgi",
            "--host", f"unix:{socket_path}",
            "--workers", str(workers),
            "--threads", str(threads),
            f"{wsgi_module}:application"
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        self.processes[app_name] = AppProcess(
            process=proc,
            app_name=app_name,
            socket_path=socket_path,
            workers=workers
        )

        # Wait for socket to exist
        for _ in range(30):
            if socket_path.exists():
                return
            await asyncio.sleep(0.1)
        raise TimeoutError(f"Socket {socket_path} never appeared")

    async def stop_app(self, app_name: str, timeout: int = 30):
        """Gracefully stop an app."""
        if app_proc := self.processes.get(app_name):
            app_proc.process.send_signal(signal.SIGTERM)
            try:
                await asyncio.wait_for(
                    app_proc.process.wait(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                app_proc.process.kill()
                await app_proc.process.wait()
            finally:
                del self.processes[app_name]
                app_proc.socket_path.unlink(missing_ok=True)

    async def reload_app(self, app_name: str):
        """Zero-downtime reload (future work)."""
        # Start new process on temp socket
        # Update Caddy to point to new socket
        # Wait for connections to drain
        # Kill old process
        pass

    async def scale_app(self, app_name: str, workers: int):
        """Scale workers by restarting with new count."""
        if app_proc := self.processes.get(app_name):
            # Stop old process
            await self.stop_app(app_name)
            # Start new with updated worker count
            # (Would need to store original config)

    async def _monitor_loop(self):
        """Health monitoring and auto-restart."""
        while self._running:
            for app_name, app_proc in list(self.processes.items()):
                if app_proc.process.returncode is not None:
                    print(f"App {app_name} died with code {app_proc.process.returncode}")
                    # Auto-restart logic would go here

            await asyncio.sleep(5)
```

### C. Caddy Configuration Example

**Caddyfile format:**
```caddy
{
    admin localhost:2019
    auto_https on
}

myapp.example.com {
    reverse_proxy unix//home/hop3/sockets/myapp.sock
}

otherapp.example.com {
    reverse_proxy unix//home/hop3/sockets/otherapp.sock
}
```

**JSON API format:**
```json
{
  "apps": {
    "http": {
      "servers": {
        "hop3": {
          "listen": [":80", ":443"],
          "routes": [
            {
              "match": [{"host": ["myapp.example.com"]}],
              "handle": [
                {
                  "handler": "reverse_proxy",
                  "upstreams": [
                    {"dial": "unix//home/hop3/sockets/myapp.sock"}
                  ]
                }
              ]
            }
          ]
        }
      }
    },
    "tls": {
      "automation": {
        "policies": [
          {
            "issuers": [{"module": "acme"}]
          }
        ]
      }
    }
  }
}
```

### D. Performance Comparison Target

**Metrics to benchmark:**
- Requests/second (should be ≥ uWSGI)
- Latency p50, p95, p99 (should be ≤ uWSGI)
- Memory usage (target: ≤ uWSGI)
- CPU usage (target: ≤ uWSGI)
- Time to start app (target: ≤ uWSGI)
- Time to reload app (target: < uWSGI)

**Test scenarios:**
1. Single app, low load (100 req/s)
2. Single app, high load (1000 req/s)
3. Multiple apps (10 apps, 100 req/s each)
4. WebSocket connections
5. Large request bodies
6. Static file serving (if applicable)
