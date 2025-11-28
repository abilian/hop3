# ADR 030: Two-Level Build Architecture

**Status**: Accepted
**Date**: 2025-11-28
**Related ADRs**: ADR 020 (Pluggable Architecture), ADR 022 (Build/Deploy Plugin System)

---

## Context

The current build system conflates two distinct architectural levels into a single hierarchy:

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

## Implementation Plan

### Phase 1: Add BuildContext + LanguageToolchain Protocol (1-2 hours)

**File**: `packages/hop3-server/src/hop3/core/protocols.py`

```python
# 1. Add BuildContext dataclass
@dataclass
class BuildContext:
    """Context for build operations.

    Contains information needed during the build phase, before deployment.
    Separate from DeploymentContext to avoid coupling build and deploy concerns.
    """
    app_name: str
    source_path: Path
    app_config: dict

    def __post_init__(self):
        assert self.source_path.is_dir()


# 2. Update existing Builder protocol
class Builder(Protocol):
    """Top-level build orchestrator."""
    name: str
    context: BuildContext  # ← Change from DeploymentContext

    def __init__(self, context: BuildContext) -> None:  # ← Change
        ...

    def accept(self) -> bool:
        """Check if this builder should be used."""

    def build(self) -> BuildArtifact:
        """Orchestrate the build process."""


# 3. Add new LanguageToolchain protocol
class LanguageToolchain(Protocol):
    """Language-specific build toolchain - defines WHAT tools to use."""
    name: str
    context: BuildContext  # ← Uses BuildContext

    def __init__(self, context: BuildContext) -> None:
        ...

    def accept(self) -> bool:
        """Check if this toolchain applies to the project."""

    def build(self) -> BuildArtifact:
        """Execute language-specific build."""
```

**File**: `packages/hop3-server/src/hop3/core/hookspecs.py`

```python
@hookspec
def get_language_toolchains() -> list[type[LanguageToolchain]]:
    """Get language-specific toolchains (PythonToolchain, NodeToolchain, etc.)

    Returns:
        List of LanguageToolchain classes for building language-specific projects.
    """
```

**Impact**: Non-breaking - adds new BuildContext and LanguageToolchain protocol alongside existing code

---

### Phase 2: Rename Existing Classes (2-4 hours)

**Strategy**: Systematic renaming using IDE refactoring tools

| Current File | Current Class | New Class | Protocol |
|--------------|---------------|-----------|----------|
| `hop3/builders/_base.py` | `Builder` (ABC) | `LanguageToolchain` | Level 2 |
| `hop3/builders/python.py` | `PythonBuilder` | `PythonToolchain` | Level 2 |
| `hop3/builders/node.py` | `NodeBuilder` | `NodeToolchain` | Level 2 |
| `hop3/builders/ruby.py` | `RubyBuilder` | `RubyToolchain` | Level 2 |
| `hop3/builders/go.py` | `GoBuilder` | `GoToolchain` | Level 2 |
| `hop3/builders/rust.py` | `RustBuilder` | `RustToolchain` | Level 2 |
| `hop3/builders/static.py` | `StaticBuilder` | `StaticToolchain` | Level 2 |
| `hop3/builders/clojure.py` | `ClojureBuilder` | `ClojureToolchain` | Level 2 |
| `hop3/builders/php.py` | `PhpBuilder` | `PhpToolchain` | Level 2 |

**Steps**:
1. Rename `hop3/builders/_base.py::Builder` → `LanguageToolchain`
2. Update all imports
3. Rename each `*Builder` class → `*Toolchain`
4. Update `hop3/builders/__init__.py`:
   ```python
   TOOLCHAIN_CLASSES: list[type[LanguageToolchain]] = [
       StaticToolchain,
       PythonToolchain,
       NodeToolchain,
       # ...
   ]
   ```

**Impact**: Breaking change - all references must be updated

---

### Phase 3: Implement LocalBuilder (4-6 hours)

**File**: `packages/hop3-server/src/hop3/plugins/build/local/builder.py`

```python
from hop3.core.protocols import Builder, LanguageToolchain, BuildContext, BuildArtifact
from hop3.builders import TOOLCHAIN_CLASSES

class LocalBuilder(Builder):
    """Build directly on host using native language toolchains.

    This is the ONLY builder that uses LanguageToolchains.
    Other builders (Docker, Nix) encapsulate their build logic differently.

    This builder:
    1. Auto-detects which language toolchains apply (Python, Node, etc.)
    2. Invokes each toolchain to build the respective components
    3. Combines artifacts if multiple toolchains are used
    """
    name = "local"

    def __init__(self, context: BuildContext) -> None:
        """Initialize local builder with build context."""
        self.context = context

    def accept(self) -> bool:
        """Always accept - local building is the default."""
        return True

    def build(self) -> BuildArtifact:
        """Build using local toolchains."""
        # 1. Discover applicable toolchains
        toolchains = self._discover_toolchains(self.context)

        if not toolchains:
            raise RuntimeError("No language toolchain detected for this project")

        # 2. Build with each toolchain (supports multi-language apps)
        artifacts = []
        for toolchain_class in toolchains:
            toolchain = toolchain_class(self.context)
            artifact = toolchain.build()
            artifacts.append(artifact)

        # 3. Single toolchain case
        if len(artifacts) == 1:
            return artifacts[0]

        # 4. Multi-toolchain case (e.g., Python + Node)
        return self._combine_artifacts(artifacts)

    def _discover_toolchains(self, context: BuildContext) -> list[type[LanguageToolchain]]:
        """Auto-detect which toolchains apply to this project.

        Example: A Python backend + Node frontend would return both
        PythonToolchain and NodeToolchain.
        """
        applicable = []
        for toolchain_class in TOOLCHAIN_CLASSES:
            # Create temporary instance to check acceptance
            toolchain = toolchain_class(context)
            if toolchain.accept():
                applicable.append(toolchain_class)
        return applicable

    def _combine_artifacts(self, artifacts: list[BuildArtifact]) -> BuildArtifact:
        """Combine multiple artifacts for multi-language apps."""
        # Simple implementation: return composite artifact
        return BuildArtifact(
            kind="multi-language",
            location=str(self.context.source_path.parent),
            metadata={"artifacts": [a.__dict__ for a in artifacts]}
        )
```

**File**: `packages/hop3-server/src/hop3/plugins/build/local/plugin.py`

```python
from hop3.core.hooks import hop3_hook_impl
from .builder import LocalBuilder

class LocalBuildPlugin:
    """Plugin that provides local build capability."""

    name = "local-build"

    @hop3_hook_impl
    def get_builders(self) -> list:
        """Return LocalBuilder for building on the host."""
        return [LocalBuilder]

# Auto-register plugin instance when module is imported
plugin = LocalBuildPlugin()
```

**Impact**: New functionality - enables proper multi-toolchain support

---

### Phase 4: Update Plugin System (1-2 hours)

**File**: `packages/hop3-server/src/hop3/plugins/build/native_build/plugin.py`

```python
from hop3.builders import TOOLCHAIN_CLASSES
from hop3.core.hooks import hop3_hook_impl

class NativeBuildPlugin:
    """Plugin that provides native language toolchains."""

    name = "native-build"

    @hop3_hook_impl
    def get_language_toolchains(self) -> list:
        """Return native toolchains for Python, Node, Ruby, etc."""
        return TOOLCHAIN_CLASSES

# Auto-register plugin instance when module is imported
plugin = NativeBuildPlugin()
```

**File**: `packages/hop3-server/src/hop3/core/plugins.py`

Update `get_build_strategy()` → `get_builder()`:

```python
def get_builder(context: BuildContext) -> Builder:
    """Find and instantiate the appropriate builder.

    Selection order:
    1. Explicit configuration: context.app_config.get("build.method", "auto")
    2. Auto-detection: First builder that accepts the context

    Args:
        context: Build context with app information

    Returns:
        Builder instance (LocalBuilder, DockerBuilder, etc.)

    Raises:
        RuntimeError: If no suitable builder is found
    """
    pm = get_plugin_manager()

    # Get all registered builders (Level 1)
    builder_classes_list = pm.hook.get_builders()
    builder_classes = [
        cls for sublist in builder_classes_list for cls in sublist
    ]

    # TODO: Check context.app_config for explicit builder selection
    builder_name_from_config = "auto"

    # Auto-detect by finding the first one that accepts
    if builder_name_from_config == "auto":
        for builder_class in builder_classes:
            builder = builder_class(context)
            if builder.accept():
                return builder

        raise RuntimeError("Could not find a suitable builder for this application")

    # Explicit builder selection
    for builder_class in builder_classes:
        if getattr(builder_class, "name", None) == builder_name_from_config:
            return builder_class(context)

    raise RuntimeError(f"Configured builder '{builder_name_from_config}' not found")
```

**Impact**: Updates orchestration logic to use new two-level system

---

### Phase 5: Fix Type Errors (30 minutes)

Now that we've split the abstractions and introduced BuildContext, the dual constructor issue disappears:

**Before** (Level 1 + Level 2 conflated, using DeploymentContext):
```python
class Builder(ABC):
    def __init__(
        self,
        app_name_or_context: str | DeploymentContext,  # ❌ Serves two purposes
        app_path: Path | None = None,
    ) -> None:
        if hasattr(app_name_or_context, "app_name"):  # ❌ Type narrowing fails
            # New plugin system path
            ...
        else:
            # Legacy path
            ...
```

**After** (Level 2 only, using BuildContext):
```python
class LanguageToolchain(ABC):
    def __init__(self, context: BuildContext) -> None:  # ✅ Single signature
        """Initialize toolchain with build context."""
        self.context = context
        self.app_name = context.app_name
        self.src_path = context.source_path
```

**Level 1 classes** (Builders) also have clean signatures with BuildContext:
```python
class LocalBuilder(Builder):
    def __init__(self, context: BuildContext) -> None:  # ✅ Single signature
        """Initialize local builder with build context."""
        self.context = context
```

**Impact**: Resolves the mypy errors without needing `isinstance()` workarounds. BuildContext properly separates build-time from deployment-time concerns.

---

### Phase 6: Update Documentation (2-3 hours)

**Files to update**:
- `docs/src/dev/architecture.md` - Add two-level build architecture section
- `CLAUDE.md` - Update with new terminology
- Plugin author guide (future) - Explain when to implement Builder vs LanguageToolchain

**Key documentation points**:
- Difference between Builder and LanguageToolchain
- When to implement each (build method vs language support)
- How multi-language builds work
- Configuration options for selecting builders

---

### Phase 7: Testing (3-4 hours)

**Test categories**:

1. **Unit tests** for new protocols:
   - `LanguageToolchain.accept()` logic
   - `LocalBuilder._discover_toolchains()`

2. **Integration tests** for builder selection:
   - `get_builder()` returns correct builder
   - Auto-detection works
   - Config-based selection works

3. **System tests** for multi-toolchain builds:
   - Python-only app builds correctly
   - Node-only app builds correctly
   - Python+Node app builds both components

4. **E2E tests** for full deployment:
   - Apps deploy successfully with LocalBuilder
   - Verify artifacts are correct

**Estimated effort**: 3-4 hours to write comprehensive tests

---

### Phase 8: Migration of Toolchains to Plugins (Future Work)

**Goal**: Move `hop3/builders/` → `hop3/plugins/toolchains/`

**Structure**:
```
hop3/plugins/toolchains/
├── python/
│   ├── toolchain.py        # PythonToolchain
│   └── plugin.py           # Plugin registration
├── node/
│   ├── toolchain.py        # NodeToolchain
│   └── plugin.py
└── java/
    ├── toolchain.py        # JavaToolchain
    └── plugin.py
```

**Benefits**:
- Toolchains become first-class plugins
- External plugins can add new language support
- Consistent architecture (all strategies are plugins)

**Effort**: 1-2 days for systematic migration

**Timeline**: After Phase 1-7 are complete and stable

---

## Timeline Summary

| Phase | Description | Estimated Time |
|-------|-------------|----------------|
| 1 | Add LanguageToolchain protocol | 1-2 hours |
| 2 | Rename existing classes | 2-4 hours |
| 3 | Implement LocalBuilder | 4-6 hours |
| 4 | Update plugin system | 1-2 hours |
| 5 | Fix type errors | 30 minutes |
| 6 | Update documentation | 2-3 hours |
| 7 | Testing | 3-4 hours |
| **Total** | **Core implementation** | **14-22 hours** (~2-3 days) |
| 8 (Future) | Migrate toolchains to plugins | 1-2 days |

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
- **Terminology Decision**: `local-notes/TERMINOLOGY-DECISION.md`
- **Related ADRs**:
  - ADR 020: Pluggable Architecture
  - ADR 022: Build/Deploy Plugin System
