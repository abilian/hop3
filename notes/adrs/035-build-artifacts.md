# ADR 035: Build Artifacts as Runtime Contract

**Status**: Accepted (NixBuilder shipping; LocalBuilder retrofit deferred)
**Type**: Architecture
**Created**: 2026-02-23
**Updated**: 2026-04-14
**Related-ADRs**: 006, 008, 022, 030, 032

## Revisions

- v1.1: Promoted from Proposed to Accepted. The `BuildArtifact` + `RuntimeConfig` contract is the basis of NixBuilder's output (`$out/hop3/runtime.json`) and is consumed without language-specific knowledge by the deploy stage. ADR 006 §"Architectural Context" and ADR 008 (template generation) both rely on this contract. Retrofitting the LocalBuilder + LanguageToolchain path so that `spawn.py` reads `RuntimeConfig` instead of doing per-language detection (`_setup_node_paths`, `_setup_python_paths`, `_setup_ruby_paths`) is deferred — it would deliver the architectural cleanliness goal stated in the original problem section but not unlock new functionality, so it ranks below the active workstreams (2026-04-14).
- v1.0: Original proposed version (2026-02-23)

## Context

During a refactoring session to reduce complexity in `spawn.py`, we extracted language-specific environment setup into helper methods:

```python
# In spawn.py make_env()
self._setup_node_paths(env)    # NODE_PATH, node_modules/.bin
self._setup_ruby_paths(env)    # GEM_HOME, BUNDLE_PATH
self._setup_python_paths(env)  # PYTHONPATH for src-layout
```

This revealed a deeper architectural issue: **the run phase has hardcoded knowledge of specific languages**.

### The Problem

1. **Violates plugin architecture**: Adding a new language requires modifying `spawn.py`, not just adding a plugin
2. **Build/run coupling**: The run phase "peeks" at build outputs to infer configuration
3. **No portability**: Runtime config is re-detected on each spawn, can't be moved between machines
4. **Nix incompatibility**: Nix computes all paths at build time; detection-based approach doesn't fit

### Current Architecture

```
BUILD PHASE                          RUN PHASE
┌─────────────┐                     ┌─────────────────────────┐
│ Toolchain   │ ──returns──▶        │ spawn.py                │
│ .build()    │   BuildArtifact     │                         │
└─────────────┘   (minimal)         │ _setup_node_paths()  ◀──┼── hardcoded
                                    │ _setup_ruby_paths()  ◀──┼── language
                                    │ _setup_python_paths()◀──┼── knowledge
                                    └─────────────────────────┘
```

The `BuildArtifact` returned by toolchains is minimal (just `kind`, `location`, `metadata`) and not persisted. The run phase must re-discover what was built.

### Design Goals

1. **Clean build/run separation**: Like Docker's `docker build` → image → `docker run`
2. **Toolchain-agnostic runtime**: `spawn.py` should not know about specific languages
3. **Portable artifacts**: Build on one machine, run on another
4. **Nix-ready**: Model must support Nix's fully-resolved paths

---

## Decision

**Extend `BuildArtifact` to include complete runtime configuration, persist it after build, and have the run phase consume it without language-specific detection.**

### New Architecture

```
BUILD PHASE                              RUN PHASE
┌─────────────┐                         ┌─────────────────────┐
│ Toolchain   │                         │ spawn.py            │
│ .build()    │ ──returns──▶            │                     │
└─────────────┘   BuildArtifact         │ _apply_artifact_    │
                  (complete)            │  runtime(env)       │
                       │                │                     │
                       ▼                │ (generic, reads     │
              ┌────────────────┐        │  artifact data)     │
              │ BUILD_ARTIFACT │        └──────────┬──────────┘
              │ .json          │ ◀─────────────────┘
              │                │        reads
              │ - env_vars     │
              │ - path_prepend │
              │ - workers      │
              └────────────────┘
```

### Data Model

```python
@dataclass
class RuntimeConfig:
    """Everything the run phase needs - computed at build time."""
    env_vars: dict[str, str]      # PYTHONPATH, NODE_PATH, etc.
    path_prepend: list[str]       # Paths to add to PATH
    working_dir: str              # Working directory for processes
    workers: dict[str, str]       # From Procfile, resolved commands

@dataclass
class BuildArtifact:
    """Self-describing build output - contract between build and run."""
    kind: str                     # "python", "node", "nix", etc.
    builder: str                  # "local", "nix", "docker"
    app_name: str
    built_at: str                 # ISO 8601
    build_id: str                 # Git SHA or UUID
    location: str                 # Root path or image reference
    runtime: RuntimeConfig        # Complete runtime configuration
    metadata: dict[str, Any]      # For debugging/auditing
```

### Key Changes

1. **Toolchains compute runtime config**: Each toolchain returns a complete `BuildArtifact` with all paths resolved
2. **Artifact is persisted**: Saved as `BUILD_ARTIFACT.json` after build
3. **Run phase is generic**: Just reads artifact and applies configuration
4. **No language detection at runtime**: All decisions made at build time

---

## Rationale

### Why Persistent Artifact (not Detection)?

We considered two approaches:

| Approach | Description | Pros | Cons |
|----------|-------------|------|------|
| **Detection** | Run phase checks for `node_modules/`, `Gemfile`, etc. | Simple, always current | Couples run to build, not portable |
| **Artifact** | Build phase records config, run phase reads it | Clean separation, portable | Extra file, could get stale |

**We chose Artifact because:**

1. **Build/run independence**: Core architectural goal - run should not know build details
2. **Portability**: Artifact can be built on one machine, run on another (future: build servers)
3. **Nix compatibility**: Nix computes everything at build time; detection doesn't fit
4. **Explicit over implicit**: Artifact is inspectable, debuggable (`cat BUILD_ARTIFACT.json`)

### Why Not Stale Data Concerns?

Detection advocates argue "what if user manually installs dependencies after build?"

This is actually **undesirable behavior** we want to prevent:
- Build should be the single source of truth
- Manual modifications should require rebuild
- This matches Docker/Nix philosophy

### Nix Integration

Nix naturally produces this model:

```python
# NixBuilder.build()
BuildArtifact(
    kind="nix",
    builder="nix",
    location="/nix/store/abc123-myapp",
    runtime=RuntimeConfig(
        env_vars={
            "PATH": "/nix/store/abc123-myapp/bin:/nix/store/def456-python/bin",
            "PYTHONPATH": "/nix/store/abc123-myapp/lib/python3.11/site-packages",
        },
        workers={"web": "/nix/store/abc123-myapp/bin/gunicorn"},
    ),
)
```

The `spawn.py` code doesn't change - it just reads the artifact.

---

## Consequences

### Positive

- **Clean architecture**: Build and run are independent phases
- **Extensible**: New languages don't require `spawn.py` changes
- **Portable**: Artifacts can move between machines
- **Debuggable**: `BUILD_ARTIFACT.json` is human-readable
- **Nix-ready**: Model aligns with Nix's build philosophy

### Negative

- **Extra file**: `BUILD_ARTIFACT.json` must be managed
- **Build required**: Can't just drop files and run (must rebuild)
- **Migration**: Existing deployments need rebuild (acceptable for MVP)

### Neutral

- **Complexity shift**: Moves complexity from run to build (appropriate placement)
- **Toolchain responsibility**: Each toolchain must produce complete config

---

## Alternatives Considered

### Alternative 1: Classmethod on Toolchain

Add `setup_runtime_env(app, env)` classmethod that detects and configures at spawn time.

```python
@classmethod
def setup_runtime_env(cls, app: App, env: Env) -> bool:
    if not (app.src_path / "node_modules").exists():
        return False
    env["NODE_PATH"] = str(app.src_path / "node_modules")
    return True
```

**Rejected because:**
- Still couples run phase to language-specific detection
- Not portable (must re-detect on each machine)
- Doesn't align with Nix model

### Alternative 2: Store Config in Database

Store runtime config in the App ORM model instead of JSON file.

**Rejected because:**
- Couples artifact to database schema
- Harder to inspect/debug
- Database not available in all contexts (e.g., build server)

### Alternative 3: Keep Hardcoded Methods

Accept that only ~5 languages need runtime setup and keep them hardcoded.

**Rejected because:**
- Violates plugin architecture promise
- Doesn't scale to new languages
- Blocks Nix integration

---

## Implementation Outline

### Phase 1: Data Model
- Create `RuntimeConfig` and extended `BuildArtifact` in `core/artifacts.py`
- Add serialization (to/from JSON)

### Phase 2: Toolchains
- Update each toolchain to return complete `BuildArtifact` with `RuntimeConfig`
- Add helper methods to base class (`_get_workers()`, `_get_build_id()`)

### Phase 3: Persistence
- Save `BUILD_ARTIFACT.json` after build in deployer

### Phase 4: Run Phase
- Add `_load_artifact()` and `_apply_artifact_runtime()` to `spawn.py`
- Remove hardcoded `_setup_*_paths()` methods

### Phase 5: Testing
- Unit tests for artifact serialization
- Integration tests for build → persist → load → run flow

---

## References

- ADR 030: Two-Level Build Architecture (Builder vs LanguageToolchain)
- ADR 032: Deployment Strategies and Artifact Lifecycle
- [The Twelve-Factor App: Build, Release, Run](https://12factor.net/build-release-run)
- [Nix: Reproducible Builds](https://nixos.org/guides/how-nix-works.html)
