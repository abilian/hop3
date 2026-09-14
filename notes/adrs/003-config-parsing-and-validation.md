# ADR 003: Config Parsing and Validation

- **Status**: Accepted
- **Type**: Feature
- **Created**: 2024-07-17
- **Related-ADRs**: [001](./001-config-files.md), [002](./002-config-format.md)

## Context

We decided early in the project to reuse an existing syntax for the `hop3.toml` files, the heart of the Hop3 platform.

We chose to favor [TOML](https://toml.io/en/) for several reasons, including:

1. **Simplicity and Readability**: TOML was designed to be simple and easy to understand for humans, making it well suited to configuration files. It aims to be more readable and straightforward than YAML or JSON, which can become complex and verbose with large data structures.
1. **Explicit and Obvious**: TOML is designed to map unambiguously to a hash table. It aims to be more explicit and less prone to errors or misinterpretation than YAML, which has more complex features like references and tags.
1. **Consistent Style**: TOML has a more consistent style, whereas YAML can be written in different ways (flow style and block style) which might cause confusion.
1. **Strong Typing**: TOML has a clear type system, including explicit types for dates and times, which JSON lacks. While YAML also supports data types, its type system can lead to surprising results due to its reliance on tags.

However, we also chose to support JSON and YAML as alternatives because the concrete syntax of the `hop3.toml` files is mostly irrelevant, as long as it produces a valid JSON object.

### Decision

- Parse the configuration once (and report errors as soon as possible), apply some transformations, and transform it into JSON which will then be the reference file (loaded by `jsonlib` when necessary, without further transformation).
- Implement schema validation for the `hop3.toml` file (see Validation Requirements below).
- Add specific code to validate the "env" section (because we don't know the keywords a priori), and possibly other sections.

### Detailed Design

Configuration access is property-based: a `Hop3Config` class parses `hop3.toml` with `tomllib`, and an `AppConfig` class merges `Procfile` and `hop3.toml`, exposing fields through property accessors. [ADR 001](./001-config-files.md) and [ADR 002](./002-config-format.md) document which fields are active.

Validation at load time is limited to TOML parse errors. Semantic errors (missing required field, wrong type) surface when the accessor runs. We defer formal schema validation to keep the dependency list empty and to iterate quickly on the config surface.

### Validation Requirements

The validation system must provide:

1. **Type Checking**
   - Verify field types match specification (string, integer, list, dict, etc.)
   - Handle optional vs required fields appropriately

2. **Required Field Validation**
   - Enforce mandatory fields (e.g., `[metadata].id` when metadata section is present)
   - Provide clear errors when required fields are missing

3. **Format Validation**
   - URL format for `website`, `src-url`, `git-url` fields
   - Version string format for `version` fields
   - Cron pattern format for scheduled tasks
   - App name format (alphanumeric + hyphens, length limits)

4. **Semantic Validation**
   - Worker type conflicts (e.g., can't have both `web` and `wsgi`)
   - Provider reference validation (env vars referencing non-existent providers)
   - Port number ranges

5. **Error Message Quality**
   - Clear, actionable error messages
   - Include line/column numbers when possible
   - Suggest fixes for common mistakes
   - Support machine-readable error format (for tooling)

### Implementation Options

Several approaches can meet the validation requirements:

| Option | Pros | Cons |
|--------|------|------|
| **Enhanced dataclasses** | No new deps, simple | Manual validation code |
| **Pydantic v2** | Rich validation, JSON Schema export | Additional dependency |
| **attrs + cattrs** | Lightweight, Pythonic | Less automatic validation |
| **msgspec** | Fast, good validation | Less mature ecosystem |
| **JSON Schema** | Language-agnostic, IDE support | Separate from Python code |

The implementation choice is left open. Any approach that meets the validation requirements is acceptable.

### Alternatives

- An ad-hoc class with `@property` accessors and no schema layer validates little: it defers semantic checks to access time, though it stays simple and dependency-free.

### Consequences

#### Benefits

- **Better Developer Experience (DX)**: Early feedback about invalid configuration syntax or basic semantics reaches developers and package-builders sooner.
- **Fewer Runtime Dependencies**: The build-time/runtime reliance on TOML or YAML parsers is avoided.
- **Easier Evolution**: The configuration format can evolve through a consistent schema.
