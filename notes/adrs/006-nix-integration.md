# ADR 006: Nix Integration with Hop3

**Status**: Accepted
**Type**: Feature
**Created**: 2024-07-17
**Related-ADRs**: 007, 008, 009, 020, 022, 030, 031, 032, 035

## Context

Hop3 is a self-hosted platform designed to streamline the deployment, management, and security of web applications. It caters to both developers and non-technical users by providing dual workflows: a `git push` or CLI-based workflow for developers and a web UI for non-technical users.

To ensure deterministic, reproducible deployments and system configurations, integrating Nix as a core component is essential. Nix offers a declarative package management system and build environment, ensuring consistency and reliability across diverse deployment scenarios. This integration aligns with Hop3's goals and the broader NGI initiative while leveraging Nix’s strengths in reproducibility, resource efficiency, and security.

Integrating Nix into Hop3 will bridge the gap between reproducible builds and practical deployment needs. Hop3 will generate Nix configurations automatically when they don't exist, convert Heroku-like config files (e.g., Procfile, app.json), and enable easy contribution to the Nix ecosystem.

### Layered Scope

Nix integration is structured as four layers of increasing scope:

| Layer | Scope | Notes |
|-------|-------|-------|
| **Layer 1** | Projects with explicit `hop3.nix` file | Applications build and deploy via hand-crafted `hop3.nix`. |
| **Layer 2** | Nixpkgs packages as Blueprints (ADR 007) | The `nixpkgs-wrapper` template in ADR 008 covers this use case (wrapping an existing nixpkgs package with Hop3 runtime metadata) more cleanly than the originally-proposed Blueprint abstraction, which it supersedes. |
| **Layer 3** | Template-based generation at build time (ADR 008) | Templates (`nixpkgs-wrapper`, `prebuilt-binary`, `prebuilt-archive`, `node-prebuilt`, `php-app`, `python-venv`, `java-war`, `ruby-bundler`) generate `hop3.nix` for common app shapes. A three-tier reproducibility taxonomy (§ADR 008) is surfaced in per-template metadata. |
| **Layer 4** | Full NixOS runtime integration (ADR 009) | Nix-managed systemd services, Nix-managed backing-service integration, NixOS module generation. |

### Architectural Context

Hop3 adopts a **two-level build architecture** (ADR 030):

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

### Layer 1: hop3.nix Support

1. **hop3.nix File Format**:

A `hop3.nix` file in the application root defines how to build and run the app. Both generated and hand-crafted expressions pin nixpkgs to a specific commit (nixos-24.11) so the toolchain is reproducible across machines and dates:

   ```nix
   # hop3.nix - minimal example
   { pkgs ? import (fetchTarball {
     url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
     sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
   }) {} }:
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

### Higher Layers

4. **Nixpkgs Integration** (Layer 2, ADR 007):
   - Deploy pre-packaged applications from nixpkgs (Nextcloud, etc.)
   - Map nixpkgs packages to Hop3 Blueprints

5. **Auto-Generation** (Layer 3, ADR 008):
   - Generate Nix expressions from requirements.txt, package.json, etc.
   - Leverage dream2nix, poetry2nix, or nixpacks

6. **Optimization** (Layer 4):
   - Binary cache integration
   - Closure size optimization
   - Build parallelization

Design questions deeper in the stack (Nix-store GC, multi-app isolation, sandbox policy) are resolved in the follow-up ADRs.

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

## File Locations

| Component | Path |
|-----------|------|
| NixBuilder | `packages/hop3-server/src/hop3/plugins/build/nix/builder.py` |
| NixBuildPlugin | `packages/hop3-server/src/hop3/plugins/build/nix/plugin.py` |
| Builder Protocol | `packages/hop3-server/src/hop3/core/protocols.py` |
| LocalBuilder (reference) | `packages/hop3-server/src/hop3/plugins/build/local_build/builder.py` |
