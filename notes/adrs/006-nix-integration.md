# ADR: Nix Integration with Hop3

## Status

Status: Draft

Versions:

- v0.1: Initial draft (2024-07-17)
- v0.2: Tweak following feedback from NLNet (2024-09-23)

## Context

Hop3 is a self-hosted platform designed to streamline the deployment, management, and security of web applications. It caters to both developers and non-technical users by providing dual workflows: a `git push` or CLI-based workflow for developers and a web UI for non-technical users.

To ensure deterministic, reproducible deployments and system configurations, integrating Nix as a core component is essential. Nix offers a declarative package management system and build environment, ensuring consistency and reliability across diverse deployment scenarios. This integration aligns with Hop3's goals and the broader NGI initiative while leveraging Nix’s strengths in reproducibility, resource efficiency, and security.

Integrating Nix into Hop3 will bridge the gap between reproducible builds and practical deployment needs. Hop3 will generate Nix configurations automatically when they don’t exist, convert Heroku-like config files (e.g., Procfile, app.json), and enable easy contribution to the Nix ecosystem.

## Decision

Hop3 will integrate Nix to take advantage of its strengths in reproducible builds and package management. This will include developing Nix packages for Hop3, creating Nix builders for existing packages, and ensuring performance and resource efficiency optimizations for build processes.

## Key Components

1. **Nix Package for Hop3**:

   - **Development**: Create a Nix package for Hop3 to ensure easy installation and management within the Nix ecosystem.
   - **Distribution**: Support distribution across Unix and Unix-like systems and ensure generated configurations can be contributed back to the Nixpkgs repository.

1. **Nix Builders for Existing Packages**:

   - **Compatibility**: Develop builder plugins for applications available in the nixpkgs repository, integrating these with Hop3's build process.
   - **Automation**: Automatically generate Nix configurations for unsupported applications, leveraging existing configurations such as Heroku config files (Procfile, app.json) or Dockerfiles.

1. **Nix Alternatives to Native Builders**:

   - **Uniform Build Environment**: Develop Nix-based alternatives to native build systems (e.g., pip, npm, Maven), ensuring uniformity in Hop3’s build and runtime environments.
   - **Leverage Existing Tools**: Utilize and contribute to projects like dream2nix, Poetry2nix, or Nixpacks to streamline the process.

1. **Optimization**:

   - **Performance**: Optimize Nix expressions for performance and resource usage (CPU, storage, network). Explore caching mechanisms to reduce build times and resource consumption.

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

1. **Development**:

   - Create the initial Nix package for Hop3.
   - Build and integrate Nix builders for existing packages, starting with low-complexity applications.

1. **Optimization**:

   - Continuously refine Nix expressions for optimal performance.
   - Develop Nix-based alternatives to native build tools and ensure seamless integration with Hop3's workflow.

1. **Community Engagement**:

   - Collaborate with the Nix community for feedback and support.
   - Provide documentation and tutorials for both developers and users to adopt Nix effectively.
