# ADR 030: Two-Level Build Architecture

- **Status**: Final
- **Type**: Feature
- **Created**: 2025-11-28
- **Implemented-In**: v0.5.0
- **Related-ADRs**: 006, 008, 020, 022, 035

## Context

A build system can conflate two distinct architectural levels into a single hierarchy:

1. **Build orchestration** (HOW to build): Should we build locally, in Docker, with Nix?
2. **Language-specific tooling** (WHAT to build): How do we build Python vs Node vs Java?

This conflation creates several problems:

### Problem 1: A Dual Constructor Reveals Architectural Confusion

A single builder base class that serves both levels needs a dual constructor, and type narrowing fails on it:

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

**Root Cause**: Such a class tries to serve two purposes:
- Abstract base for language toolchains (Python, Node, Java)
- Plugin interface for build orchestration (invoked by plugin system)

### Problem 2: A Flat Hierarchy Cannot Support Multiple Build Methods

A flat hierarchy:
```
Builder (Protocol)
  ├── PythonBuilder
  ├── NodeBuilder
  ├── StaticBuilder
  └── DummyBuilder
```

**Issues**:
- A `DockerBuilder` that builds ALL languages in containers has no clean place in the hierarchy.
- A `NixBuilder` that builds ALL languages with Nix has no clean place either.
- Python+Node in a single app (full-stack) cannot be expressed.

A flat hierarchy treats all `*Builder` classes equally in the plugin system, but:
- `PythonBuilder` is language-specific (Level 2)
- `DockerBuilder` is language-agnostic (Level 1)
- They belong to different architectural levels

### Problem 3: Composite and Alternative Builds

**Multi-language builds**: A Python backend + Node frontend needs:
- One orchestrator: `LocalBuilder`
- Two toolchains: `PythonToolchain` + `NodeToolchain`

A flat hierarchy cannot express this cleanly.

**Alternative build methods**: Users want to choose:
- Local builds (fast, uses host tools)
- Docker builds (reproducible, isolated)
- Nix builds (reproducible, declarative)
- Buildpack builds (Heroku/Cloud Foundry compatibility)

A flat hierarchy mixes these concerns with language-specific logic.

---

## Decision

Hop3 adopts a **two-level build architecture** that separates orchestration from language-specific tooling:

- **Builder** (Level 1) decides *how* to build: local, Docker, or Nix.
- **LanguageToolchain** (Level 2) decides *what* to build: Python, Node, Go, Rust, Ruby, Java, PHP, or a generic fallback.

Only the `LocalBuilder` delegates to LanguageToolchains. `DockerBuilder` and `NixBuilder` bypass the LanguageToolchain layer entirely: their build logic lives inside the Dockerfile or the Nix expression (see [ADR 006](006-nix-integration.md) §"Architectural Context" and [ADR 008](008-nix-builders-2.md)).

### BuildContext vs DeploymentContext

The protocols rest on a separation of build-time and deployment-time concerns:

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

**Protocol**: `LanguageToolchain` (in `hop3/core/protocols.py`)
**Responsibility**: Execute WHAT to build (dependencies, compilation, bundling)
**Examples**: `PythonToolchain`, `NodeToolchain`, `JavaToolchain`, `RubyToolchain`
**Selection**: Auto-detection (presence of requirements.txt, package.json, etc.)
**Hook**: `get_language_toolchains()`
**Location**: `hop3/plugins/build/language_toolchains/`

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
- The `Builder` protocol in `hop3/core/protocols.py` lives at this level

**Consistency with Terminology**:
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

⚠️ **Renaming and restructuring**: The original language-specific `*Builder` classes become `*Toolchain`, and the original `Builder` ABC becomes `LanguageToolchain`.

⚠️ **Complexity**: Two protocols instead of one
- Requires clear documentation
- Plugin authors need to understand the distinction

### Neutral

🔄 **Backwards Compatibility**: A single `get_builders()` hook can return both Builders and LanguageToolchains, so the split can be introduced before the hooks are separated into `get_builders()` and `get_language_toolchains()`.

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

## References

- **Plugin System**: `packages/hop3-server/src/hop3/core/plugins.py`
- **Related ADRs**:
  - ADR 020: Pluggable Architecture
  - ADR 022: Build/Deploy Plugin System
