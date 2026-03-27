# ADR 030: Two-Level Build Architecture

**Status**: Final
**Type**: Feature
**Created**: 2025-11-28
**Implemented-In**: v0.5.0
**Related-ADRs**: 020, 022, 035

## Context

> **Note**: This section describes the problems that existed *before* this ADR was implemented.
> The two-level architecture is now in place and working.

The original build system conflated two distinct architectural levels into a single hierarchy:

1. **Build orchestration** (HOW to build): Should we build locally, in Docker, with Nix?
2. **Language-specific tooling** (WHAT to build): How do we build Python vs Node vs Java?

This conflation creates several problems:

### Problem 1: Type Error Reveals Architectural Confusion

The mypy error in `hop3/builders/_base.py` is a symptom of deeper confusion:

```python
def __init__(
    self,
    app_name_or_context: str | DeploymentContext,  # Dual constructor
    app_path: Path | None = None,
) -> None:
    if hasattr(app_name_or_context, "app_name"):  # ❌ Type narrowing fails
        context = app_name_or_context
        self.app_path = context.source_path.parent  # ❌ Type error
```

**Root Cause**: This class tries to serve two purposes:
- Abstract base for language toolchains (Python, Node, Java)
- Plugin interface for build orchestration (invoked by plugin system)

### Problem 2: Cannot Support Multiple Build Methods

Current flat hierarchy:
```
Builder (Protocol)
  ├── PythonBuilder
  ├── NodeBuilder
  ├── StaticBuilder
  └── DummyBuilder
```

**Issues**:
- How do we add `DockerBuilder` that builds ALL languages in containers?
- How do we add `NixBuilder` that builds ALL languages with Nix?
- How do we support Python+Node in a single app (full-stack)?

All `*Builder` classes are treated equally by the plugin system, but:
- `PythonBuilder` is language-specific (Level 2)
- `DockerBuilder` would be language-agnostic (Level 1)
- They belong to different architectural levels

### Problem 3: Future Requirements

**Multi-language builds**: A Python backend + Node frontend needs:
- One orchestrator: `LocalBuilder`
- Two toolchains: `PythonToolchain` + `NodeToolchain`

Current architecture cannot express this cleanly.

**Alternative build methods**: Users want to choose:
- Local builds (fast, uses host tools)
- Docker builds (reproducible, isolated)
- Nix builds (reproducible, declarative)
- Buildpack builds (Heroku/Cloud Foundry compatibility)

Current flat hierarchy mixes these concerns with language-specific logic.

---

## Decision

We adopt a **two-level build architecture** that separates orchestration from language-specific tooling.

### BuildContext vs DeploymentContext

Before defining the protocols, we need to separate build-time and deployment-time concerns:

```python
@dataclass
class BuildContext:
    """Context for build operations (before deployment).

    Contains information needed during the build phase, before deployment.
    Separate from DeploymentContext to avoid coupling build and deploy concerns.
    """
    app_name: str
    source_path: Path
    app_config: dict

    def __post_init__(self):
        assert self.source_path.is_dir()


@dataclass
class DeploymentContext:
    """Context for deployment operations (after build).

    Contains information needed during the deployment phase, after build.
    """
    app_name: str
    source_path: Path
    app_config: dict
    app: App | None = None  # The full App object from the database

    def __post_init__(self):
        assert self.source_path.is_dir()
```

**Rationale**: Build and deployment are two independent phases. Builders operate during the build phase and don't need deployment-specific information like the database `App` object.

### Level 1: Builder (Orchestration)

**Protocol**: `Builder` (in `hop3/core/protocols.py`)
**Responsibility**: Orchestrate HOW to build (environment, isolation, reproducibility)
**Examples**: `LocalBuilder`, `DockerBuilder`, `NixBuilder`, `BuildpackBuilder`
**Selection**: Config-driven (global or per-app `hop3.toml`)
**Hook**: `get_builders()`
**Location**: `hop3/plugins/build/*/` (e.g., `hop3/plugins/build/local/`)

```python
class Builder(Protocol):
    """Top-level build orchestrator - defines HOW to build.

    Builders orchestrate the build process and may delegate to language
    toolchains for language-specific operations.

    Examples:
    - LocalBuilder: Builds on host using native language toolchains
    - DockerBuilder: Builds in container using Dockerfile
    - NixBuilder: Builds with Nix for reproducibility
    """
    name: str
    context: BuildContext

    def __init__(self, context: BuildContext) -> None:
        """Initialize the builder with a build context."""

    def accept(self) -> bool:
        """Check if this builder should be used for the given context."""

    def build(self) -> BuildArtifact:
        """Orchestrate the build process and return the artifact."""
```

### Level 2: LanguageToolchain (Language-Specific Logic)

**Protocol**: `LanguageToolchain` (new protocol in `hop3/core/protocols.py`)
**Responsibility**: Execute WHAT to build (dependencies, compilation, bundling)
**Examples**: `PythonToolchain`, `NodeToolchain`, `JavaToolchain`, `RubyToolchain`
**Selection**: Auto-detection (presence of requirements.txt, package.json, etc.)
**Hook**: `get_language_toolchains()`
**Location**:
- **Currently**: `hop3/builders/` (will be renamed)
- **Future**: `hop3/plugins/toolchains/` (will become plugins)

```python
class LanguageToolchain(Protocol):
    """Language-specific build toolchain - defines WHAT tools to use.

    Toolchains handle language-specific build operations like installing
    dependencies, compiling code, and bundling assets.

    Examples:
    - PythonToolchain: Uses pip/uv, creates virtualenv, compiles .pyc
    - NodeToolchain: Uses npm/yarn, runs webpack, transpiles JS
    - JavaToolchain: Uses maven/gradle, compiles .class files
    """
    name: str
    context: BuildContext

    def __init__(self, context: BuildContext) -> None:
        """Initialize the toolchain with a build context."""

    def accept(self) -> bool:
        """Check if this toolchain applies to the project.

        Examples:
        - PythonToolchain: checks for requirements.txt or pyproject.toml
        - NodeToolchain: checks for package.json
        """

    def build(self) -> BuildArtifact:
        """Execute language-specific build and return the artifact."""
```

---

## Rationale

### Why Two Levels?

**Separation of Concerns**:
- **Level 1 (Builder)**: Environment and isolation concerns
  - Where to build? (host, container, sandbox)
  - How to isolate? (none, Docker, Nix)
  - What resources? (CPU, memory, network access)

- **Level 2 (LanguageToolchain)**: Language-specific concerns
  - What package manager? (pip, npm, maven)
  - How to install dependencies?
  - How to compile/transpile code?

**Orthogonal Variation**:
- `LocalBuilder` uses LanguageToolchains to build on the host
- `DockerBuilder` encapsulates build logic in Dockerfile (no toolchains)
- `NixBuilder` uses Nix expressions (no toolchains)

LanguageToolchains are specific to LocalBuilder and enable:
- Multi-language builds (Python + Node in a single app)
- Auto-detection of applicable languages
- Reusable language-specific build logic

### Why "Builder" at Level 1?

**Domain Language**:
- DevOps engineers ask: "What builder are you using?"
- They mean: "Are you building locally, in Docker, or with Nix?"
- The current `Builder` protocol in `hop3/core/protocols.py` already exists at this level

**Consistency with Terminology Decision (ADR-TERMINOLOGY)**:
- Follows Heroku-inspired naming (Builder, Deployer, Addon)
- Avoids generic suffixes like "Strategy" or "Method"
- Natural and concrete term

### Why "LanguageToolchain" at Level 2?

**Established Terminology**:
- "Python toolchain", "Node toolchain" are industry-standard terms
- Refers to the set of tools needed to build a language (pip, virtualenv, compiler, etc.)
- More specific than generic "backend" or "strategy"

**Avoids Confusion**:
- "Backend" could mean server-side code (vs frontend)
- "Toolchain" is unambiguous: the build tools for a language

---

## Consequences

### Positive

✅ **Clear Separation of Concerns**: Build orchestration and language tooling are distinct

✅ **Multi-Language Support**: One `LocalBuilder` can use multiple toolchains
```python
# Full-stack app: Python backend + Node frontend
builder = LocalBuilder(context)
artifact = builder.build()

# Inside LocalBuilder.build() implementation:
# - Discovers both PythonToolchain and NodeToolchain
# - Builds with each: python_artifact, node_artifact
# - Combines them into a single artifact
```

✅ **Extensibility**: Easy to add new builders (Nix, Buildpack) or toolchains (Rust, Go)

✅ **Type Safety**: Clear protocol boundaries enable proper type checking

✅ **Solves the Type Error**: The dual constructor issue goes away when we split the abstraction

### Negative

⚠️ **Breaking Change**: Requires renaming and restructuring
- `hop3/builders/*Builder` → `*Toolchain`
- Current `Builder` ABC → `LanguageToolchain`
- Affects ~10 files

⚠️ **Migration Effort**: Must update all builder implementations
- Estimated: 1-2 days for renaming and restructuring
- Estimated: Additional time for new `LocalBuilder` implementation

⚠️ **Complexity**: Two protocols instead of one
- Requires clear documentation
- Plugin authors need to understand the distinction

### Neutral

🔄 **Backwards Compatibility**: The plugin hook can remain `get_builders()` initially
- Return both Builders and LanguageToolchains
- Gradually migrate to separate hooks

🔄 **Gradual Migration**: Can implement incrementally
- Phase 1: Add `LanguageToolchain` protocol
- Phase 2: Rename existing classes
- Phase 3: Implement `LocalBuilder`
- Phase 4: Move toolchains to plugins

---

## Implementation Status

> **All core phases are complete.** The two-level build architecture is fully implemented.

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Add BuildContext + LanguageToolchain protocol | ✅ Complete |
| 2 | Rename existing classes to `*Toolchain` | ✅ Complete |
| 3 | Implement LocalBuilder | ✅ Complete |
| 4 | Update plugin system | ✅ Complete |
| 5 | Fix type errors | ✅ Complete |
| 6 | Update documentation | ✅ Complete |
| 7 | Testing | ✅ Complete |
| 8 | Rename directory `builders/` → `toolchains/` | Pending (low priority) |

### Current File Locations

**Protocols** (`packages/hop3-server/src/hop3/core/protocols.py`):
- `Builder` - Level 1 protocol (orchestration)
- `LanguageToolchain` - Level 2 protocol (language-specific)
- `BuildContext` - Context for build operations
- `BuildArtifact` - Describes built output (extended with `RuntimeConfig` in ADR 035)

**LocalBuilder** (`packages/hop3-server/src/hop3/plugins/build/local_build/builder.py`):
- Orchestrates toolchains for local builds
- Auto-detects applicable toolchains
- Supports multi-language builds

**LanguageToolchains** (`packages/hop3-server/src/hop3/builders/`):
- `_base.py` - `LanguageToolchain` ABC
- `python.py` - `PythonToolchain`
- `node.py` - `NodeToolchain`
- `ruby.py` - `RubyToolchain`
- `go.py` - `GoToolchain`
- `rust.py` - `RustToolchain`
- `clojure.py` - `ClojureToolchain`
- `php.py` - `PHPToolchain`
- `static.py` - `StaticToolchain`
- `__init__.py` - Exports `TOOLCHAIN_CLASSES`

### Remaining Work

**Directory rename** (low priority):
- Rename `hop3/builders/` → `hop3/toolchains/` for consistency
- The directory contains toolchains, not builders

---

## Alternative Approaches Considered

### Alternative 1: Keep Flat Hierarchy, Add Marker Attribute

```python
class Builder(Protocol):
    name: str
    is_orchestrator: bool = False  # True for Docker/Nix, False for Python/Node
```

**Rejected**:
- Doesn't solve the type narrowing issue
- Still mixes two concerns in one abstraction
- Unclear semantics (what does `is_orchestrator` mean?)

---

### Alternative 2: Use Composition Instead of Protocols

```python
class Builder:
    def __init__(self, toolchains: list[LanguageToolchain]):
        self.toolchains = toolchains
```

**Rejected**:
- Doesn't work for DockerBuilder (doesn't use toolchains)
- Forces all builders to use the same pattern
- Less flexible than protocol-based approach

---

### Alternative 3: Single Builder, Strategy Pattern for Toolchains

Keep `Builder` at Level 1, but have it use a "ToolchainStrategy" internally.

**Rejected**:
- Adds unnecessary indirection
- Still need to rename existing classes
- More complex than two protocols

---

## Future Considerations

### Multi-Language Configuration

Users may need to configure which toolchains to use:

```toml
# hop3.toml
[build]
method = "local"  # or "docker", "nix"
toolchains = ["python", "node"]  # Explicit toolchain selection

[build.python]
package_manager = "uv"  # or "pip", "poetry"

[build.node]
package_manager = "pnpm"  # or "npm", "yarn"
```

### Toolchain Dependencies

Some toolchains may depend on others:
- TypeScript toolchain depends on Node toolchain
- Sass toolchain depends on Node toolchain

May need dependency resolution in the future.

### Performance Optimization

Building with multiple toolchains sequentially may be slow. Consider:
- Parallel builds (if toolchains are independent)
- Incremental builds (cache toolchain outputs)
- Artifact reuse (don't rebuild unchanged components)

---

## Success Metrics

This architecture is successful when:

1. ✅ Multi-language apps (Python + Node) build correctly
2. ✅ New build methods (Docker, Nix) can be added without changing toolchains
3. ✅ New language toolchains can be added as plugins
4. ✅ Type checking passes with no errors or `# type: ignore` comments
5. ✅ Plugin authors understand when to implement Builder vs LanguageToolchain

---

## References

- **Current Builder Implementation**: `packages/hop3-server/src/hop3/builders/_base.py`
- **Current Plugin System**: `packages/hop3-server/src/hop3/core/plugins.py`
- **Related ADRs**:
  - ADR 020: Pluggable Architecture
  - ADR 022: Build/Deploy Plugin System
