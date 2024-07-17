# ADR: Config File(s) for Hop3

## Status

Status: Draft (v0.1)

## Context

The Hop3 platform requires a robust and flexible method for defining configurations and metadata for deploying and managing web applications. Initially, the focus was on a single configuration file format to streamline the process. However, the need for flexibility and compatibility with existing standards led to the consideration of multiple configuration file formats.

The core configurations and metadata for a given Hop3 package can be provided in various forms, including:

1. **hop3.toml**: The primary configuration file designed for simplicity, readability, and explicitness.
2. **Procfile**: A file that defines process types and commands for a web application, widely used in platforms like Heroku.
3. **Other Files and Scripts**: Various other files and scripts that can provide necessary configuration and metadata, ensuring compatibility with different deployment environments and user preferences.

## Decision

To support a diverse range of use cases and existing workflows, Hop3 will allow configuration and metadata to be provided through multiple file formats. The decision includes the following key points:

- **Primary Configuration**: The `hop3.toml` file will serve as the primary configuration file, providing a clear and human-readable format.
- **Alternative Formats**: Support for alternative formats such as Procfiles and other configuration scripts will be maintained to ensure flexibility and compatibility.
- **Unified Parsing and Validation**: Regardless of the format, all configuration files will be parsed and validated to ensure consistency and correctness.

## Alternatives

- A single configuration file format (e.g., only supporting `hop3.toml`), which would simplify the implementation but reduce flexibility and compatibility.
- Ad-hoc configuration methods without a unified structure, leading to potential inconsistencies and increased complexity in management.

## Consequences

### Benefits

- **Flexibility**: Users can choose the configuration file format that best suits their needs and existing workflows.
- **Compatibility**: Maintains compatibility with widely-used standards and existing deployment scripts.
- **Ease of Transition**: Facilitates easier migration from other platforms by supporting common configuration formats.

### Drawbacks

- **Complexity in Implementation**: Supporting multiple formats requires additional parsing and validation logic.
- **Potential for Inconsistencies**: Ensuring consistency across different formats can be challenging.

## Action Items

1. **Support for Multiple Formats**:
- Implement parsing logic for `hop3.toml`, Procfiles, and other relevant configuration formats.
- Ensure all formats can be transformed into a unified internal representation for processing.

2. **Validation Framework**:
- Develop a validation framework that works across different configuration formats, ensuring consistency and correctness.
- Use Pydantic for schema validation and custom logic for format-specific validation requirements.

3. **Documentation and Examples**:
- Provide comprehensive documentation detailing the supported configuration formats and their usage.
- Include examples and best practices for each supported format to guide users in setting up their configurations.

4. **Tooling and Integration**:
- Develop CLI tools to assist users in generating and validating their configuration files.
- Integrate configuration validation into the CI/CD pipeline to catch errors early in the development cycle.

5. **Community Feedback and Iteration**:
- Gather feedback from the community on the supported formats and their usability.
- Iterate on the implementation based on user feedback to improve the overall developer experience.
