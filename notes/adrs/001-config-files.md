# ADR 001: Config Files for Hop3

- **Status**: Accepted
- **Type**: Feature
- **Created**: 2024-07-17
- **Related-ADRs**: [002](./002-config-format.md), [003](./003-config-parsing-and-validation.md)

## Summary

This ADR proposes that Hop3 support multiple configuration file formats for flexibility and compatibility with existing standards. The primary configuration file will be `hop3.toml`, supplemented by Procfiles and other relevant scripts.

## Context and Goals

The Hop3 platform needs a flexible configuration method for deploying and managing web applications. A single configuration file format was considered initially for simplicity. The need for compatibility with existing standards led to the consideration of multiple formats. The core configurations and metadata for a given Hop3 package can be provided in various forms, including:

1. **hop3.toml**: The primary configuration file, designed for simplicity and readability.
1. **Procfile**: A file that defines process types and commands for a web application, widely used in platforms like Heroku.
1. **Other Files and Scripts**: Various other files and scripts that supply configuration and metadata, ensuring compatibility with different deployment environments and user preferences.

## Decision

Hop3 will support configuration and metadata through multiple file formats to accommodate diverse use cases and existing workflows:

- **Primary Configuration**: The `hop3.toml` file serves as the primary configuration file and provides a clear, human-readable format.
- **Alternative Formats**: Procfiles and other configuration scripts are supported for flexibility and compatibility.
- **Unified Parsing and Validation**: All configuration files are parsed and validated to ensure consistency and correctness.

A Hop3 application's configuration surface is bounded to `Procfile` + `hop3.toml`. Ad-hoc configuration scripts (Dockerfile-flavoured shell snippets, inline Python) are out of scope: builders and deployers are plugin-based, and per-app scripts have no place in that model.

## Consequences

### Benefits

- **Flexibility**: Users choose the configuration file format that suits their needs and existing workflows.
- **Compatibility**: Compatible with widely-used standards and existing deployment scripts.
- **Ease of Transition**: Migration from other platforms is easier because common configuration formats are supported.

### Drawbacks

- **Complexity in Implementation**: Supporting multiple formats requires additional parsing and validation logic.
- **Potential for Inconsistencies**: Consistency across different formats is harder to maintain than a single format.

## Alternatives

- A single configuration file format (e.g., only `hop3.toml`), which would simplify the implementation but reduce flexibility and compatibility.
- Ad-hoc configuration methods without a unified structure, which lead to inconsistencies and complicate management.
- Additional serialization formats (YAML, JSON) as alternatives to TOML. TOML-only is sufficient for the configuration surface; further formats would be a mechanical translation layer over the same model, adding surface with no expressive gain.

Schema validation beyond TOML parse errors is owned by [ADR 003](./003-config-parsing-and-validation.md). A dataclass plus `@property` model catches structural errors at access time; load-time schema validation and a `hop3 validate` command for CI gating build on that model.

## Related

- ADR #002: Detailed `hop3.toml` Format
- ADR #003: Config Parsing and Validation

## References

- TOML documentation: https://toml.io/en/
- Procfile documentation: https://devcenter.heroku.com/articles/procfile


