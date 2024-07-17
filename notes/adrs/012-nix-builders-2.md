# ADR: Creation of Nix Alternatives to Native Builders

## Status

Draft (v0.1)

## Context & Goals

To provide a uniform build process within Hop3, creating Nix-based alternatives to native build systems (e.g., pip, make, maven, npm) is essential. This approach will leverage Nix's features for build isolation and environment reproducibility, ensuring consistent and reliable builds across different environments.

Creating Nix-based alternatives to native build systems will provide a uniform, reproducible, and isolated build process within Hop3. This approach aligns with Hop3's goals of providing a reliable, efficient, and user-friendly deployment process.

## Decision

Hop3 will create Nix-based alternatives to native build systems, facilitating a uniform build process and leveraging Nix's strengths in build isolation and reproducibility.

## Key Components

1. **Development of Nix Alternatives**:
   - **Uniform Build Process**: Create Nix-based alternatives to native build systems (e.g., pip, make, maven, npm).
   - **Build Isolation**: Ensure build isolation and environment reproducibility using Nix.

2. **Leverage Existing Projects**:
   - **Study Existing Projects**: Study and potentially leverage existing projects like dream2nix, pip2nix, or nixpacks to aid in this process.

## Consequences

### Benefits

- **Uniformity**: Ensures a uniform build process across different environments.
- **Reproducibility**: Guarantees reproducible builds, crucial for debugging and collaboration.
- **Build Isolation**: Enhanced build isolation to prevent dependency conflicts.

### Drawbacks

- **Initial Development Effort**: Requires significant development effort to create Nix-based alternatives.
- **Learning Curve**: Developers may need to learn and adapt to Nix-based build processes.

## Risks

- **Complexity**: High complexity in creating Nix-based alternatives for various build systems. Mitigation involves thorough testing and community feedback.
- **Adoption**: Potential resistance from developers used to native build systems. Mitigation includes providing comprehensive documentation and tutorials.

## Action Items

1. **Development**:
   - Develop Nix-based alternatives to native build systems.
   - Ensure build isolation and reproducibility using Nix.

2. **Testing and Optimization**:
   - Conduct thorough testing to ensure reliability and performance.
   - Continuously optimize the build processes based on feedback and testing results.

3. **Documentation and Community Engagement**:
   - Provide comprehensive documentation for Nix-based build processes.
   - Engage with the Nix and Hop3 communities for feedback and contributions.
