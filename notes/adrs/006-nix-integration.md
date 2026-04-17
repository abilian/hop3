# ADR 006: Nix Integration with Hop3

**Status**: Accepted (Phase 1 + Phase 3 shipped; Phase 2 subsumed by Phase 3; Phase 4 deferred)
**Type**: Feature
**Created**: 2024-07-17
**Updated**: 2026-04-14
**Related-ADRs**: 007, 008, 009, 020, 022, 030, 031, 032, 035

## Revisions

- v0.4: Phase 3 (ADR 008) productionized across 22+ hand-crafted and 20 template-generated apps. Phase 2 (ADR 007) effectively superseded by the `nixpkgs-wrapper` template; ADR 007 is marked Superseded. Phase-status table refreshed (2026-04-14).
- v0.3: Phased approach starting with hop3.nix; align with plugin architecture (2026-03-23)
- v0.2: Tweak following feedback from NLNet (2024-09-23)
- v0.1: Initial draft (2024-07-17)

## Context

Hop3 is a self-hosted platform designed to streamline the deployment, management, and security of web applications. It caters to both developers and non-technical users by providing dual workflows: a `git push` or CLI-based workflow for developers and a web UI for non-technical users.

To ensure deterministic, reproducible deployments and system configurations, integrating Nix as a core component is essential. Nix offers a declarative package management system and build environment, ensuring consistency and reliability across diverse deployment scenarios. This integration aligns with Hop3's goals and the broader NGI initiative while leveraging Nix’s strengths in reproducibility, resource efficiency, and security.

Integrating Nix into Hop3 will bridge the gap between reproducible builds and practical deployment needs. Hop3 will generate Nix configurations automatically when they don't exist, convert Heroku-like config files (e.g., Procfile, app.json), and enable easy contribution to the Nix ecosystem.

### Phased Implementation Approach (Updated 2026-04)

| Phase | Scope | Status | Evidence |
|-------|-------|--------|----------|
| **Phase 1** | Projects with explicit `hop3.nix` file | **Shipped** | 22+ applications under `apps/real-apps-nix/` build and deploy via hand-crafted `hop3.nix`. |
| **Phase 2** | Nixpkgs packages as Blueprints (ADR 007) | **Superseded by Phase 3** | The `nixpkgs-wrapper` template in ADR 008 covers this use case (wrapping an existing nixpkgs package with Hop3 runtime metadata) more cleanly than the originally-proposed Blueprint abstraction. |
| **Phase 3** | Template-based generation at build time (ADR 008) | **Shipped** | Eight templates (`nixpkgs-wrapper`, `prebuilt-binary`, `prebuilt-archive`, `node-prebuilt`, `php-app`, `python-venv`, `java-war`, `ruby-bundler`) cover 20 applications in `apps/real-apps-nix-gen/`. Three-tier reproducibility taxonomy (§ADR 008) surfaced in per-template metadata. |
| **Phase 4** | Full NixOS runtime integration (ADR 009) | **Deferred** | Nix-managed systemd services, Nix-managed backing-service integration, NixOS module generation. Not blocking current goals. |

### Architectural Context (Updated 2026-03)

Since this ADR was written, Hop3 has adopted a **two-level build architecture** (ADR 030):

- **Level 1 - Builders**: Orchestrate HOW to build (LocalBuilder, DockerBuilder, NixBuilder)
- **Level 2 - LanguageToolchains**: Execute WHAT to build (PythonToolchain, NodeToolchain, etc.)

**NixBuilder is a Level 1 Builder** that does NOT delegate to LanguageToolchains. Instead, all build logic is encapsulated in the Nix expression (`hop3.nix`).

```
LocalBuilder                    NixBuilder
    │                               │
    ▼                               ▼
┌─────────────────┐          ┌─────────────────┐
│ PythonToolchain │          │ hop3.nix        │
│ NodeToolchain   │          │ (user-provided) │
│ RubyToolchain   │          │                 │
└─────────────────┘          └─────────────────┘
```

Additionally, Hop3 uses **BuildArtifact with RuntimeConfig** (ADR 035) as the contract between build and run phases. This model aligns perfectly with Nix:

- Nix computes all runtime paths (PATH, PYTHONPATH, etc.) at build time
- These are stored in the BuildArtifact's `RuntimeConfig`
- The run phase simply applies the artifact - no detection needed

```python
# NixBuilder.build() returns:
BuildArtifact(
    kind="nix",
    builder="nix",
    location="/nix/store/abc123-myapp",
    runtime=RuntimeConfig(
        env_vars={"PATH": "/nix/store/.../bin", "PYTHONPATH": "..."},
        path_prepend=[],
        working_dir="/nix/store/abc123-myapp",
        workers={"web": "/nix/store/.../bin/gunicorn app:app"},
    ),
)
```

## Decision

Hop3 will integrate Nix to take advantage of its strengths in reproducible builds and package management. This will include developing Nix packages for Hop3, creating Nix builders for existing packages, and ensuring performance and resource efficiency optimizations for build processes.

## Key Components

### Phase 1: hop3.nix Support (Current Focus)

1. **hop3.nix File Format**:

   A `hop3.nix` file in the application root defines how to build and run the app:

   ```nix
   # hop3.nix - minimal example
   { pkgs ? import <nixpkgs> {} }:
   {
     # Required: the built package
     package = pkgs.python3Packages.buildPythonApplication {
       pname = "myapp";
       version = "1.0.0";
       src = ./.;
       propagatedBuildInputs = with pkgs.python3Packages; [
         flask
         gunicorn
       ];
     };

     # Required: worker commands
     workers = {
       web = "gunicorn app:app --bind unix:$HOP3_SOCKET";
     };

     # Optional: additional environment variables
     env = {
       FLASK_ENV = "production";
     };
   }
   ```

2. **NixBuilder Implementation**:

   ```python
   # packages/hop3-server/src/hop3/plugins/build/nix/builder.py

   @dataclass
   class NixBuilder:
       """Build applications with user-provided hop3.nix."""

       name: str = "nix"
       context: BuildContext

       def accept(self) -> bool:
           """Accept if hop3.nix exists."""
           return (self.context.source_path / "hop3.nix").exists()

       def build(self) -> BuildArtifact:
           """Build using hop3.nix and extract RuntimeConfig."""
           # 1. Run nix-build on hop3.nix
           result = self._run_nix_build()

           # 2. Extract runtime config from Nix output
           runtime = self._extract_runtime_config(result)

           # 3. Return BuildArtifact
           return BuildArtifact(
               kind="nix",
               builder="nix",
               app_name=self.context.app_name,
               built_at=datetime.now().isoformat(),
               build_id=result.nix_hash,
               location=result.store_path,
               runtime=runtime,
               metadata={"nix_file": "hop3.nix"},
           )
   ```

3. **Configuration**:

   ```toml
   # hop3.toml
   [build]
   method = "nix"

   [build.nix]
   file = "hop3.nix"  # Default, can override
   pure = true        # Pure evaluation (recommended)
   ```

### Future Phases (Deferred)

4. **Nixpkgs Integration** (Phase 2, ADR 007):
   - Deploy pre-packaged applications from nixpkgs (Nextcloud, etc.)
   - Map nixpkgs packages to Hop3 Blueprints

5. **Auto-Generation** (Phase 3, ADR 008):
   - Generate Nix expressions from requirements.txt, package.json, etc.
   - Leverage dream2nix, poetry2nix, or nixpacks

6. **Optimization** (Phase 4):
   - Binary cache integration
   - Closure size optimization
   - Build parallelization

## Consequences

### Benefits

- **Deterministic Deployments**: Reproducible and reliable application deployments.
- **Reproducibility**: Guarantees consistent outputs from the same source inputs, crucial for debugging, security, and collaboration.
- **Resource Efficiency**: Optimized builds and resource usage across the platform.
- **Enhanced Security**: Simplified and secure dependency management, reducing the attack surface.

### Drawbacks

- **Integration Complexity**: Significant effort is required to integrate Nix across various applications and environments.
- **Learning Curve**: Developers and users will need to familiarize themselves with Nix.

## Risks

- **Integration Complexity**: High complexity in integrating diverse applications with Nix. Early community engagement and sufficient buffer time will mitigate this risk.
- **Dependency Management**: Medium probability of encountering unsupported dependencies in the Nix ecosystem. Prioritize applications with Nix support and work on packaging missing dependencies as part of the project.

## Action Items

### Phase 1: hop3.nix Support (M1.1)

1. **NixBuilder Plugin**:
   - [ ] Create `NixBuilder` class implementing `Builder` protocol
   - [ ] Implement `accept()` - check for `hop3.nix` existence
   - [ ] Implement `build()` - run `nix-build` and extract RuntimeConfig
   - [ ] Register via `NixBuildPlugin` with `get_builders()` hook

2. **hop3.nix Evaluation**:
   - [ ] Define expected attributes (`package`, `workers`, `env`)
   - [ ] Parse Nix output to extract store paths
   - [ ] Map to `RuntimeConfig` structure

3. **Integration Testing**:
   - [ ] Create sample Python app with hop3.nix
   - [ ] Verify build produces correct BuildArtifact
   - [ ] Test deployment via standard deployers (uWSGI, etc.)

4. **Documentation**:
   - [ ] Document hop3.nix file format
   - [ ] Create tutorial for Nix-based deployment
   - [ ] Add troubleshooting guide

### Future Phases (Deferred)

5. **Phase 2** (ADR 007): Nixpkgs/Blueprint integration
6. **Phase 3** (ADR 008): Auto-generation via dream2nix/nixpacks
7. **Phase 4** (ADR 009): NixOS runtime integration

Deferred design questions (Nix-store GC, multi-app isolation, sandbox policy) are tracked internally and folded into the follow-up ADRs as they land.

## File Locations

| Component | Path |
|-----------|------|
| NixBuilder | `packages/hop3-server/src/hop3/plugins/build/nix/builder.py` |
| NixBuildPlugin | `packages/hop3-server/src/hop3/plugins/build/nix/plugin.py` |
| Builder Protocol | `packages/hop3-server/src/hop3/core/protocols.py` |
| LocalBuilder (reference) | `packages/hop3-server/src/hop3/plugins/build/local_build/builder.py` |
