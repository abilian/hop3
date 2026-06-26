# ADR 001: Config Files for Hop3

- **Status**: Accepted
- **Type**: Feature
- **Created**: 2024-07-17
- **Related-ADRs**: 002, 003

## Summary

This ADR proposes the adoption of multiple configuration file formats for the Hop3 platform to enhance flexibility, compatibility, and user preference alignment. The primary configuration file will be `hop3.toml`, supplemented by support for Procfiles and other relevant scripts.

## Context and Goals

The Hop3 platform needs a robust and flexible configuration method for deploying and managing web applications. Initially, a single configuration file format was considered to streamline the process. However, the need for flexibility and compatibility with existing standards has led to the consideration of multiple configuration file formats. The core configurations and metadata for a given Hop3 package can be provided in various forms, including:

1. **hop3.toml**: The primary configuration file designed for simplicity, readability, and explicitness.
1. **Procfile**: A file that defines process types and commands for a web application, widely used in platforms like Heroku.
1. **Other Files and Scripts**: Various other files and scripts that can provide necessary configuration and metadata, ensuring compatibility with different deployment environments and user preferences.

## Decision

Hop3 will support configuration and metadata through multiple file formats to accommodate diverse use cases and existing workflows. The decision includes the following key points:

- **Primary Configuration**: The `hop3.toml` file serves as the primary configuration file, providing a clear and human-readable format.
- **Alternative Formats**: Alternative formats such as Procfiles and other configuration scripts are supported to ensure flexibility and compatibility.
- **Unified Parsing and Validation**: Regardless of the format, all configuration files are parsed and validated to ensure consistency and correctness.

A Hop3 application's configuration surface is bounded to `Procfile` + `hop3.toml`. Arbitrary ad-hoc configuration scripts (Dockerfile-flavoured shell snippets, inline Python) are out of scope: builders and deployers live in plugins, not in per-app scripts.

## Consequences

### Benefits

- **Flexibility**: Users can choose the configuration file format that best suits their needs and existing workflows.
- **Compatibility**: Maintains compatibility with widely-used standards and existing deployment scripts.
- **Ease of Transition**: Facilitates easier migration from other platforms by supporting common configuration formats.

### Drawbacks

- **Complexity in Implementation**: Supporting multiple formats requires additional parsing and validation logic.
- **Potential for Inconsistencies**: Ensuring consistency across different formats can be challenging.

## Alternatives

- A single configuration file format (e.g., only supporting `hop3.toml`), which would simplify the implementation but reduce flexibility and compatibility.
- Ad-hoc configuration methods without a unified structure, leading to potential inconsistencies and increased complexity in management.
- Additional serialization formats (YAML, JSON) as alternatives to TOML. TOML-only is sufficient for the configuration surface; further formats would be a mechanical translation layer over the same model and add surface without expressive gain.

Schema validation beyond TOML parse errors is owned by ADR 003. A dataclass plus `@property` model catches structural errors at access time; load-time schema validation, together with a `hop3 validate` command for CI gating, builds on that model.

## Related

- ADR #002: Detailed `hop3.toml` Format
- ADR #003: Config Parsing and Validation

## References

- TOML documentation: https://toml.io/en/
- Procfile documentation: https://devcenter.heroku.com/articles/procfile

## Notes

- The decision to support multiple configuration formats aims to cater to diverse user needs and existing workflows, thereby enhancing the overall flexibility and usability of the Hop3 platform.
