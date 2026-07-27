# ADR 007: Nix Builders for Existing Packages (Nixpkgs Mode)

- **Status**: Superseded
- **Type**: Feature
- **Created**: 2024-07-17
- **Superseded-By**: [ADR 008](./008-nix-builders-2.md)
- **Related-ADRs**: [006](./006-nix-integration.md), [008](./008-nix-builders-2.md), [009](./009-nix-runtime.md), [020](./020-pluggable-architecture.md), [022](./022-build-deploy-plugin-system.md), [030](./030-two-level-build-architecture.md), [031](./031-project-terminology.md), [035](./035-build-artifacts.md)

## Supersession Note

Wrapping an existing nixpkgs package does not require a dedicated "nixpkgs-mode builder" sitting alongside the hand-crafted-`hop3.nix` path. It is cleaner as one template among others in the template-based generation system. The operator selects the `nixpkgs-wrapper` template in `[nix].template`; the generator produces a thin `hop3.nix` that wraps `pkgs.<app>` with the Hop3 runtime wrapper and the [ADR 035](./035-build-artifacts.md) `runtime.json` contract.

The original goals below (reuse nixpkgs packages, automate updates, provide an app-store-like UX) remain valid, and are achieved through [ADR 008](./008-nix-builders-2.md) plus the [ADR 035](./035-build-artifacts.md) `RuntimeConfig` contract. The body of this ADR is retained for historical reference.

## Context & Goals

Hop3 aims to simplify the deployment, management, and security of web applications through deterministic and reproducible builds. Nix, as a declarative package manager, offers a robust framework for achieving this, with a vast ecosystem of packages in the nixpkgs repository.

The integration of Nix builders for existing packages is critical to enhancing Hop3’s compatibility and flexibility. Given the goal to package 20 real-world applications for Hop3, this effort will support a broad spectrum of technologies, including Python, PHP, Node.js, Ruby, Go, and Java, by leveraging Nix’s ability to provide reproducible builds and a uniform build environment. Hop3 will reuse existing Nix configurations from the nixpkgs repository where available and automatically generate Nix configurations for applications that don’t have existing Nix support.

The goal is to integrate applications into the Hop3 platform, streamline updates, and ensure compatibility with the nixpkgs repository, reducing the effort required to deploy and maintain these applications.

### Architectural Context

In Hop3's two-level build architecture ([ADR 030](./030-two-level-build-architecture.md)):

- **NixBuilder** is a **Level 1 Builder** - it orchestrates the build process
- Unlike LocalBuilder, NixBuilder does **not** use Level 2 LanguageToolchains
- Instead, it uses Nix expressions (from nixpkgs or generated) to handle all languages uniformly

This ADR focuses on **reusing existing nixpkgs packages** - applications already packaged in the Nix ecosystem (Nextcloud, Jitsi, etc.). [ADR 008](./008-nix-builders-2.md) covers generating Nix expressions for applications without existing Nix support.

**BuildArtifact Integration ([ADR 035](./035-build-artifacts.md))**: NixBuilder produces a `BuildArtifact` with fully-resolved Nix store paths in the `RuntimeConfig`. This is a natural fit since Nix computes all paths at build time.

## Decision

Hop3 will develop NixBuilder (a Level 1 Builder per [ADR 030](./030-two-level-build-architecture.md)) that supports applications available in the nixpkgs repository or those that can be converted into Nix configurations using existing tools such as dream2nix, Poetry2nix, or Nixpacks. This builder will automate the integration of Nix-built applications within the Hop3 platform, providing a consistent experience for both developers and non-technical users.

## Key Components

1. **Builder Plugin Development**:

   - **Compatibility**: Ensure the builder plugin supports existing applications in the nixpkgs repository, allowing users to deploy widely used software like Nextcloud, Jitsi, and other open-source applications efficiently.
   - **Automation**: Generate Nix configurations for unsupported applications by converting from other formats, such as Dockerfiles, Heroku config files, or native Hop3 configurations.

1. **Streamlined Updates and Maintenance**:

   - **Automated Updates**: Implement mechanisms for automatic updates and rebuilds of Nix-built applications within Hop3, ensuring users always have access to the latest software versions and patches.
   - **Dependency Management**: Use Nix’s precise dependency management to handle updates reliably, ensuring consistent environments during application upgrades.

1. **Integration with Hop3 Workflow**:

   - **App Store-Like Experience**: For non-technical users, provide a streamlined UI experience to deploy these Nix-packaged applications with minimal configuration.
   - **CLI Support for Developers**: Enable developers to deploy applications through a familiar CLI, while Nix handles the complexities of package management and reproducibility in the background.

## Consequences

### Benefits

- **Increased Compatibility**: Broadens the range of applications that can be deployed on Hop3, leveraging the extensive Nix package repository and Nix community efforts.
- **Reproducibility**: Ensures deterministic builds and environments, making debugging, collaboration, and maintenance more straightforward.
- **Automated Updates**: Reduced operational overhead through automated update and rebuild mechanisms for applications.

### Drawbacks

- **Initial Development Effort**: Building and maintaining Nix builders will require a significant upfront investment in time and resources.
- **Nix Ecosystem Complexity**: Adapting existing applications to Nix may present challenges, especially for complex software with non-trivial dependencies.

## Risks

- **Integration Complexity**: Ensuring that a wide variety of applications, particularly legacy or non-12-factor apps, are compatible with Nix and Hop3. This can be mitigated through community feedback and thorough testing with real-world applications.
- **Ongoing Maintenance**: Keeping the builder plugin in sync with changes in the nixpkgs repository and updates to the supported applications. This will require a well-defined maintenance schedule and active community contributions.
- **Performance Overhead**: Nix-based builds, while reproducible, can sometimes introduce performance overhead compared to native build systems. Mitigation involves continuous optimization of build processes and leveraging Nix’s caching mechanisms.
nisms.
