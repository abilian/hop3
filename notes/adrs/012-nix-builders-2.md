# ADR: Creation of Nix Alternatives to Native Builders

## Status

Status: Draft

Versions:
- v0.1: Initial draft (2024-07-17)
- v0.2: Tweak following feedback from NLNet (2024-09-23)

## Context & Goals

Hop3 aims to streamline application deployment and management by leveraging Nix to provide deterministic and reproducible builds. In order to achieve a uniform and isolated build process across diverse applications and environments, creating Nix-based alternatives to native build systems (e.g., pip, make, maven, npm) is essential. This ensures that applications built on Hop3 follow the same reproducible and isolated environment, reducing the complexity of managing multiple build tools and preventing conflicts in dependencies.

Hop3 will reuse existing Nix expressions from the nixpkgs repository where available, and where such expressions do not exist, will generate Nix configurations for applications automatically, including converting from Dockerfiles, Heroku config files, or Hop3-native formats. The use of Nix will guarantee that builds are reproducible across environments, enhancing the stability and maintainability of deployed applications.

## Decision

Hop3 will develop Nix-based alternatives to native build systems, facilitating a uniform, reproducible, and isolated build process for all applications. This approach will leverage existing projects, such as dream2nix, pip2nix, and nixpacks, to convert applications using common build systems (e.g., Python, Node.js, PHP) into Nix expressions, ensuring seamless integration into Hop3.

## Key Components

1. **Development of Nix-Based Alternatives**:
   - **Uniform Build Process**: Create Nix-based alternatives to native build systems (e.g., pip, npm, Maven, Make) to ensure a consistent and reliable build process across Hop3.
   - **Build Isolation and Reproducibility**: Leverage Nix’s strengths in isolating builds and ensuring reproducibility across environments. Applications built using Nix will be able to take full advantage of Nix’s dependency management, ensuring that the same build process yields identical results across different environments.

2. **Leveraging Existing Projects**:
   - **Study and Integrate Existing Tools**: Leverage existing projects like dream2nix, Poetry2nix, or nixpacks to simplify the creation of Nix expressions from native build configurations. This will allow Hop3 to automate the generation of Nix configurations for a wide range of applications, speeding up the onboarding of new applications and reducing the manual effort required to create Nix configurations.

## Consequences

### Benefits

- **Uniformity**: Ensures a consistent, uniform build process across all applications deployed on Hop3, regardless of the technology stack used.
- **Reproducibility**: Guarantees that builds are reproducible, meaning the same inputs will always produce the same outputs, which is critical for debugging, collaboration, and compliance.
- **Build Isolation**: Enhanced build isolation prevents conflicts between dependencies, providing a more secure and reliable deployment process.

### Drawbacks

- **Initial Development Effort**: The creation of Nix-based alternatives to multiple native build systems requires a significant upfront development effort. Adapting various build systems (e.g., Maven, pip, npm) to Nix-based workflows is complex.
- **Learning Curve**: Developers used to native build systems will need to learn and adapt to the Nix-based build processes, which may slow adoption initially.

## Risks

- **Complexity in Creation**: The process of creating Nix-based alternatives for complex build systems like Maven or npm can introduce significant complexity. To mitigate this, Hop3 will rely on existing projects (e.g., dream2nix) and tools in the Nix ecosystem to streamline the creation of these alternatives.
- **Developer Adoption**: Developers familiar with native build systems may resist adopting Nix-based workflows due to the learning curve. This risk will be mitigated by providing comprehensive documentation, tutorials, and clear migration paths for developers to transition from their existing workflows to Nix.

## Action Items

1. **Development**:
   - Develop Nix-based alternatives to common native build systems (pip, npm, Maven, Make) and integrate them into Hop3’s build process.
   - Generate Nix configurations automatically for applications that don’t already have Nix expressions, using tools like dream2nix or nixpacks to automate conversion from Dockerfiles, Procfiles, or native build configurations.

2. **Testing and Optimization**:
   - Conduct thorough testing on different applications to ensure that the Nix-based build process is reliable and performs well across a variety of technology stacks.
   - Continuously optimize the build processes to reduce performance overhead and ensure that Nix expressions are as efficient as possible.

3. **Documentation and Community Engagement**:
   - Provide clear and detailed documentation for developers to understand how to use Nix-based build systems within Hop3, including step-by-step guides for converting native build configurations into Nix expressions.
   - Engage with both the Nix and Hop3 communities to gather feedback on the Nix-based build system, and incorporate contributions from the broader Nix ecosystem to improve and maintain the system.
