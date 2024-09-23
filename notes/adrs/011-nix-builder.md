# ADR: Development of Nix Builders for Existing Packages

## Status

Status: Draft

Versions:

- v0.1: Initial draft (2024-07-17)
- v0.2: Tweak following feedback from NLNet (2024-09-23)

## Context & Goals

Hop3 aims to simplify the deployment, management, and security of web applications through deterministic and reproducible builds. Nix, as a declarative package manager, offers a robust framework for achieving this, with a vast ecosystem of packages in the nixpkgs repository.

The integration of Nix builders for existing packages is critical to enhancing Hop3’s compatibility and flexibility. Given the goal to package 20 real-world applications for Hop3, this effort will support a broad spectrum of technologies, including Python, PHP, Node.js, Ruby, Go, and Java, by leveraging Nix’s ability to provide reproducible builds and a uniform build environment. Hop3 will reuse existing Nix configurations from the nixpkgs repository where available and automatically generate Nix configurations for applications that don’t have existing Nix support.

The goal is to integrate applications into the Hop3 platform, streamline updates, and ensure compatibility with the nixpkgs repository, reducing the effort required to deploy and maintain these applications.

## Decision

Hop3 will develop a builder plugin that supports applications available in the nixpkgs repository or those that can be converted into Nix configurations using existing tools such as dream2nix, Poetry2nix, or Nixpacks. This builder will automate the integration of Nix-built applications within the Hop3 platform, providing a seamless experience for both developers and non-technical users.

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

## Action Items

1. **Development**:

   - Develop the initial builder plugin for Hop3, ensuring broad compatibility with applications in the nixpkgs repository.
   - Implement tools to convert non-Nix configurations (e.g., Dockerfiles, Procfile) into Nix-compatible formats.

1. **Testing and Optimization**:

   - Conduct thorough testing with several initial packaged applications to validate the builder plugin’s robustness, focusing on applications with varying levels of complexity (e.g., Nextcloud, Jitsi, simpler tools like HedgeDoc).
   - Optimize Nix expressions and build processes to minimize performance overhead.

1. **Documentation and Community Engagement**:

   - Provide clear, user-friendly documentation for both developers and non-technical users on how to use the Nix builder within Hop3.
   - Engage with the Nix and Hop3 communities for feedback and contributions, ensuring ongoing support and improvements to the builder plugin.
