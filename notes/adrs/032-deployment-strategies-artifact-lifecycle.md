# ADR 032: Deployment Strategies and Artifact Lifecycle

**Status**: Proposed
**Date**: 2025-12-03
**Related ADRs**: ADR 022 (Build/Deploy Plugin System), ADR 030 (Two-Level Build Architecture), ADR 031 (Terminology)

---

## Context

Currently, Hop3 uses a simple "stop-then-deploy" approach for redeployments: when deploying a new version of a running application, it stops the old version, builds and deploys the new version, then starts it. This approach has significant limitations:

1. **Downtime**: The application is unavailable during the entire build and deploy process
2. **No rollback**: If the new version fails to start, the old version is already gone
3. **In-place modification**: Build artifacts are created in the same location, destroying the previous version

### The Artifact Problem

Build artifacts in Hop3 can take many forms:

| Artifact Type | Example | Storage | Startable? |
|---------------|---------|---------|------------|
| **Virtualenv** | `/apps/myapp/venv/` | Directory | Via uWSGI/gunicorn |
| **Node modules** | `/apps/myapp/node_modules/` | Directory | Via node/pm2 |
| **Container image** | `myapp:v1.2.3` | Registry/local | Via docker/podman |
| **Binary** | `/apps/myapp/bin/server` | File | Direct execution |
| **Static files** | `/apps/myapp/dist/` | Directory | Via nginx |
| **VM image** | `myapp-v1.2.3.qcow2` | File | Via libvirt/QEMU |
| **Nix closure** | `/nix/store/xxx-myapp/` | Immutable store | Via Nix |

Each artifact type has different characteristics:
- **Mutability**: Can it be modified in place? (Nix closures: no, virtualenvs: yes)
- **Versioning**: How are versions tracked? (Git SHA, semantic version, content hash)
- **Storage**: Where does it live? (filesystem, registry, object store)
- **Startup**: How is it started? (process manager, container runtime, systemd)

### Current Flow (Stop-Then-Deploy)

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Receive    │────▶│    Stop     │────▶│   Build     │────▶│   Start     │
│  new code   │     │  old app    │     │  new app    │     │   new app   │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                          │                    │
                          ▼                    ▼
                    ⚠️ DOWNTIME          Old artifact
                    starts here          overwritten
```

**Problems**:
- Downtime = stop time + build time + start time (can be minutes)
- If build fails, app stays down
- If new version fails to start, no automatic recovery
- No way to quickly rollback

---

## Decision

### 1. Artifacts as First-Class Versioned Entities

Build artifacts become versioned, immutable entities stored separately from the "current" deployment:

```
/apps/myapp/
├── artifacts/                    # Versioned artifacts
│   ├── v1.2.3/                  # or git SHA, or timestamp
│   │   ├── venv/
│   │   ├── static/
│   │   └── manifest.json        # Artifact metadata
│   ├── v1.2.4/
│   │   └── ...
│   └── v1.2.5/
│       └── ...
├── current -> artifacts/v1.2.5/  # Symlink to active version
├── previous -> artifacts/v1.2.4/ # Previous version for rollback
├── src/                          # Source code (latest)
└── shared/                       # Shared data (uploads, logs, etc.)
```

#### Artifact Manifest

Each artifact includes metadata for lifecycle management:

```json
{
  "version": "v1.2.5",
  "build_id": "abc123",
  "git_sha": "f8a9c3d",
  "built_at": "2025-12-03T10:30:00Z",
  "builder": "local",
  "toolchains": ["python"],
  "artifact_type": "virtualenv",
  "health_check": {
    "type": "http",
    "path": "/health",
    "timeout": 30
  },
  "rollback_safe": true,
  "migration_status": "pending"
}
```

### 2. Deployment Strategies

Different strategies for different needs:

#### Strategy A: Stop-Then-Deploy (Current)

**Use case**: Development, simple applications, acceptable downtime

```
Stop old → Build new → Start new
```

- ✅ Simple implementation
- ✅ Low resource usage (single instance)
- ❌ Downtime during build
- ❌ No automatic rollback

#### Strategy B: Blue-Green Deployment (Recommended for Production)

**Use case**: Production applications requiring zero downtime

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  ┌─────────┐    ┌─────────────┐    ┌─────────────┐             │
│  │ Build   │───▶│ Start new   │───▶│ Health      │             │
│  │ new     │    │ (port 8001) │    │ check       │             │
│  └─────────┘    └─────────────┘    └──────┬──────┘             │
│                                           │                     │
│                                    ┌──────┴──────┐              │
│                                    │  Healthy?   │              │
│                                    └──────┬──────┘              │
│                              Yes ┌────────┴────────┐ No         │
│                                  ▼                 ▼            │
│                         ┌─────────────┐    ┌─────────────┐      │
│  Old app (port 8000) ◀──│ Switch      │    │ Keep old    │      │
│  keeps running          │ proxy       │    │ Report error│      │
│                         └──────┬──────┘    └─────────────┘      │
│                                │                                │
│                                ▼                                │
│                         ┌─────────────┐                         │
│                         │ Stop old    │                         │
│                         │ (graceful)  │                         │
│                         └─────────────┘                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

- ✅ Zero downtime
- ✅ Instant rollback (switch proxy back)
- ✅ New version validated before switch
- ❌ Requires 2x resources during deploy
- ❌ Complex proxy management

#### Strategy C: Rolling Deployment

**Use case**: Scaled applications with multiple workers

```
Workers: [W1-old] [W2-old] [W3-old] [W4-old]
           ↓
         [W1-NEW] [W2-old] [W3-old] [W4-old]
           ↓
         [W1-NEW] [W2-NEW] [W3-old] [W4-old]
           ↓
         [W1-NEW] [W2-NEW] [W3-NEW] [W4-old]
           ↓
         [W1-NEW] [W2-NEW] [W3-NEW] [W4-NEW]
```

- ✅ Gradual rollout
- ✅ Can stop if issues detected
- ❌ Mixed versions during rollout
- ❌ Requires stateless workers

#### Strategy D: Canary Deployment

**Use case**: Risk-sensitive production deployments

```
Route 5% traffic to new version
Monitor errors/latency
If OK → increase to 25%, 50%, 100%
If bad → rollback immediately
```

- ✅ Minimal blast radius
- ✅ Real production testing
- ❌ Complex routing logic
- ❌ Requires traffic splitting support

### 3. Artifact Lifecycle State Machine

```
                    ┌─────────┐
                    │ BUILDING│
                    └────┬────┘
                         │ build success
                         ▼
                    ┌─────────┐
                    │  READY  │ (stored, not deployed)
                    └────┬────┘
                         │ deploy
                         ▼
                    ┌─────────┐
            ┌──────▶│ STARTING│
            │       └────┬────┘
            │            │ health check pass
            │            ▼
            │       ┌─────────┐
   rollback │       │ RUNNING │◀────────┐
            │       └────┬────┘         │
            │            │ new deploy   │ rollback
            │            ▼              │
            │       ┌─────────┐         │
            └───────│PREVIOUS │─────────┘
                    └────┬────┘
                         │ cleanup (after N versions)
                         ▼
                    ┌─────────┐
                    │ ARCHIVED│
                    └─────────┘
```

### 4. Database Migrations

Database migrations are the hardest problem in zero-downtime deployments.

#### Migration Strategies

| Strategy | How it works | Trade-offs |
|----------|--------------|------------|
| **Pre-deploy** | Run migrations before deploy | Old code must handle new schema |
| **Post-deploy** | Run migrations after deploy | New code must handle old schema |
| **Expand-Contract** | Add new → migrate data → remove old | Safest but slowest |
| **Blue-Green DB** | Separate databases, sync after | Complex, data sync issues |

#### Recommended Approach: Backwards-Compatible Migrations

1. **Expand phase** (pre-deploy):
   - Add new columns (nullable or with defaults)
   - Add new tables
   - Create new indexes

2. **Deploy new code**:
   - New code uses new schema
   - Old code still works (ignores new columns)

3. **Contract phase** (post-deploy, after rollback window):
   - Remove old columns
   - Drop old tables
   - Remove compatibility code

```python
# Example: Renaming a column

# Phase 1: Expand (pre-deploy)
# Migration adds new column, copies data
ALTER TABLE users ADD COLUMN full_name VARCHAR(255);
UPDATE users SET full_name = name;

# Phase 2: Deploy
# New code reads/writes full_name
# Old code still reads/writes name

# Phase 3: Contract (after rollback window)
# Migration removes old column
ALTER TABLE users DROP COLUMN name;
```

#### Migration Manifest

```json
{
  "migration_id": "20251203_rename_user_name",
  "phase": "expand",
  "backwards_compatible": true,
  "rollback_safe": true,
  "requires_downtime": false,
  "estimated_duration": "30s",
  "pre_deploy": ["add_full_name_column"],
  "post_deploy": ["drop_name_column"]
}
```

### 5. Shared Resources and State

#### Resource Categories

| Resource | Strategy | Notes |
|----------|----------|-------|
| **Uploads/media** | Shared directory | `/apps/myapp/shared/uploads/` |
| **Session data** | External store | Redis, database |
| **Cache** | Version-specific | Clear on deploy or use versioned keys |
| **Logs** | Shared directory | `/apps/myapp/shared/logs/` |
| **Sockets** | Version-specific | `myapp-v1.sock`, `myapp-v2.sock` |
| **Ports** | Dynamic allocation | Allocate from pool during deploy |

#### Socket/Port Management for Blue-Green

```python
class PortAllocator:
    """Manages ports for blue-green deployments."""

    def allocate(self, app_name: str, version: str) -> int:
        """Allocate a port for a new version."""
        # Options:
        # 1. Dynamic port allocation (8000-9000 range)
        # 2. Version-based: base_port + version_hash % 100
        # 3. Blue/green alternating: 8000 (blue), 8001 (green)

    def release(self, app_name: str, version: str) -> None:
        """Release port when version is stopped."""
```

### 6. Implementation Phases

#### Phase 1: Versioned Artifacts (Foundation)

- [ ] Add artifact versioning (directory structure)
- [ ] Store artifact manifest with metadata
- [ ] Keep N previous versions (configurable)
- [ ] Add `hop3 releases` command to list versions
- [ ] Add `hop3 rollback <app> [version]` command

#### Phase 2: Health Checks

- [ ] Define health check interface in artifact manifest
- [ ] Implement HTTP health check
- [ ] Implement TCP health check
- [ ] Implement command health check
- [ ] Add timeout and retry configuration

#### Phase 3: Blue-Green Deployment

- [ ] Implement port/socket allocation for parallel versions
- [ ] Start new version alongside old
- [ ] Run health checks on new version
- [ ] Switch proxy configuration atomically
- [ ] Graceful shutdown of old version

#### Phase 4: Migration Support

- [ ] Add migration phase to deployment workflow
- [ ] Pre-deploy and post-deploy hooks
- [ ] Migration status tracking
- [ ] Rollback-safe migration validation

#### Phase 5: Advanced Strategies

- [ ] Rolling deployment for scaled workers
- [ ] Canary deployment with traffic splitting
- [ ] Automatic rollback on error threshold

---

## Consequences

### Positive

1. **Zero-downtime deployments**: Applications stay available during updates
2. **Instant rollback**: Can revert to previous version in seconds
3. **Deployment confidence**: New versions are validated before receiving traffic
4. **Audit trail**: Full history of deployments and artifacts
5. **Resource efficiency**: Artifacts are immutable and can be cached/shared

### Negative

1. **Increased complexity**: More moving parts to manage
2. **Storage requirements**: Multiple versions consume more disk space
3. **Migration discipline**: Requires backwards-compatible migration practices
4. **Resource overhead**: Blue-green requires 2x resources during deploy

### Neutral

1. **Learning curve**: Teams need to understand deployment strategies
2. **Configuration**: More options to configure per application
3. **Monitoring**: Need to track deployment metrics and health

---

## Alternatives Considered

### 1. Always In-Place (Current Approach)

Keep the simple stop-then-deploy approach for all cases.

**Rejected because**: Unacceptable for production workloads requiring high availability.

### 2. Container-Only

Require all applications to be containerized, leveraging container orchestration for deployment strategies.

**Rejected because**: Hop3's value proposition includes supporting non-containerized applications. However, containerized apps naturally get blue-green via container orchestration.

### 3. External Orchestrator Integration

Delegate to Kubernetes, Nomad, or similar for deployment strategies.

**Rejected because**: Adds significant complexity and infrastructure requirements. May be offered as an optional plugin for larger deployments.

---

## References

- [The Twelve-Factor App: Build, Release, Run](https://12factor.net/build-release-run)
- [Martin Fowler: Blue Green Deployment](https://martinfowler.com/bliki/BlueGreenDeployment.html)
- [Kubernetes Deployment Strategies](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#strategy)
- [GitHub: Database Migrations at Scale](https://github.blog/engineering/database-migrations-at-scale/)
- [Expand and Contract Pattern](https://www.tim-wellhausen.de/papers/ExpandAndContract.pdf)

---

## Appendix A: Configuration Example

```toml
# hop3.toml

[deploy]
strategy = "blue-green"  # or "stop-deploy", "rolling", "canary"

[deploy.health_check]
type = "http"
path = "/health"
interval = 5
timeout = 30
healthy_threshold = 2
unhealthy_threshold = 3

[deploy.rollback]
automatic = true
error_threshold = 0.05  # 5% error rate triggers rollback
window = "5m"

[deploy.artifacts]
keep_versions = 5
cleanup_delay = "24h"

[deploy.migration]
strategy = "pre-deploy"  # or "post-deploy", "manual"
timeout = "5m"
```

## Appendix B: CLI Commands

```bash
# List artifact versions
hop3 releases myapp
# VERSION   BUILT AT              STATUS    SIZE
# v1.2.5    2025-12-03 10:30:00   running   45MB
# v1.2.4    2025-12-02 15:20:00   previous  44MB
# v1.2.3    2025-12-01 09:15:00   archived  43MB

# Rollback to previous version
hop3 rollback myapp
# Rolling back myapp to v1.2.4...
# Health check passed
# Switched traffic to v1.2.4
# Stopped v1.2.5

# Rollback to specific version
hop3 rollback myapp v1.2.3

# Deploy with specific strategy
hop3 deploy myapp --strategy=blue-green

# Check deployment status
hop3 deploy:status myapp
# Deployment in progress...
# Old version: v1.2.4 (running, receiving traffic)
# New version: v1.2.5 (starting, health check 2/3)
```
