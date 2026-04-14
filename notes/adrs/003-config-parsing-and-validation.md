# ADR 003: Config Parsing and Validation

**Status**: Accepted (phased — Phase 1 shipped, Phase 2 deferred)
**Type**: Feature
**Created**: 2024-07-17
**Updated**: 2026-04-14
**Related-ADRs**: 001, 002

## Revisions

- v0.4: Promoted from Draft to Accepted (phased). Phase 1 (dataclass + `@property`) is the shipped approach; Phase 2 (schema validation with a choice between enhanced dataclasses / Pydantic v2 / attrs+cattrs / msgspec / JSON Schema) remains open as a future enhancement (2026-04-14).
- v0.3: Replaced Pydantic-specific language with generic validation requirements (2025-12-15)
- v0.2: Clarified current implementation vs planned migration (2025-11-25)
- v0.1: Initial draft (2024-07-17)

## Context

We have decided, early on in the project, to use an existing syntax (instead of creating a new DSL) for the `hop3.toml` files, which are the heart of the Hop3 platform.

We chose to favor [TOML](https://toml.io/en/) for several reasons, including:

1. **Simplicity and Readability**: TOML was designed to be simple and easy to understand for humans, making it great for configuration files. It aims to be more readable and straightforward than YAML or JSON, which can become complex and verbose with large data structures.
1. **Explicit and Obvious**: TOML is designed to map unambiguously to a hash table. It aims to be more explicit and less prone to errors or misinterpretation than YAML, which has more complex features like references and tags.
1. **Consistent Style**: TOML has a more consistent style, whereas YAML can be written in different ways (flow style and block style) which might cause confusion.
1. **Strong Typing**: TOML has a clear type system, including explicit types for dates and times, which JSON lacks. While YAML also supports data types, its type system can sometimes lead to surprising results due to its reliance on tags.

However, we also choose to support JSON and YAML as alternatives because the concrete syntax of the `hop3.toml` files is mostly irrelevant, as long as it produces a valid JSON object.

### Decision

- Parse the configuration once (and report errors as soon as possible), apply some transformations, and transform it into JSON which will then be the reference file (loaded by `jsonlib` when necessary, but without any further transformations, or as little as possible).
- Implement schema validation for the `hop3.toml` file (see Validation Requirements below).
- Add specific code to validate the "env" section (because we don't know the keywords a priori), and possibly other sections.

### Current Implementation Status (Phase 1 — Shipped)

The current implementation uses property-based access via Python dataclasses and `@property` methods. Key files:

- `packages/hop3-server/src/hop3/project/hop3_config.py` — `Hop3Config` class with `tomllib` parsing.
- `packages/hop3-server/src/hop3/project/config.py` — `AppConfig` class merging `Procfile` + `hop3.toml` with property-based access.

Validation at load time is limited to TOML parse errors; semantic errors (missing required field, wrong type) surface when the accessor runs. This is the shipped, in-production behaviour. The trade-off is explicit: we defer formal schema validation in exchange for zero additional dependencies and fast iteration on the config surface. ADR 001 and ADR 002 document which fields are active.

### Phase 2 (Deferred) — Schema Validation

A full schema-validation layer remains an open design question. The **Validation Requirements** section below captures what any future implementation must deliver; the **Implementation Options** table captures the candidate approaches. A decision is not yet made and is not blocking current work.

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

The validation requirements can be met by several approaches:

| Option | Pros | Cons |
|--------|------|------|
| **Enhanced dataclasses** | No new deps, simple | Manual validation code |
| **Pydantic v2** | Rich validation, JSON Schema export | Additional dependency |
| **attrs + cattrs** | Lightweight, Pythonic | Less automatic validation |
| **msgspec** | Fast, good validation | Less mature ecosystem |
| **JSON Schema** | Language-agnostic, IDE support | Separate from Python code |

The implementation choice is left open - any approach that meets the validation requirements is acceptable.

### Alternatives

- Status quo (ad-hoc class with `@properties`) - **currently in use**, limited validation

### Consequences

#### Benefits

- **Better Developer Experience (DX)**: Early feedback to developers or package-builders about invalid configuration syntax or basic semantics will lead to a better developer experience.
- **Fewer Runtime Dependencies**: The build-time/runtime on TOML or YAML parsers is avoided.
- **Easier Evolution**: The configuration format can evolve more easily as it is defined and validated through a consistent schema.

### Action Items

- [ ] **Implement schema validation**: Add validation meeting the requirements above
- [ ] **Converge the configuration format**: Ensure consistency between:
  - The schema (as implemented)
  - The documentation (ADR 002)
  - The existing configuration files in examples

### Additional TODOs

1. **Documentation and Examples**:

- Provide comprehensive documentation for the configuration format, including examples for TOML, JSON, and YAML.
- Create a migration guide for users transitioning from older configuration formats to the new standardized format.

2. **Validation Enhancements**:

- Extend validation to cover more complex configurations and interdependencies between sections.
- Implement validation for additional configuration sections, ensuring completeness and correctness.

3. **Tooling and Integration**:

- Develop CLI tools to validate configuration files before deployment.
- Integrate configuration validation into the CI/CD pipeline to catch errors early in the development cycle.

4. **Error Handling and Reporting**:

- Improve error messages to be more descriptive and helpful, guiding users to fix issues quickly.
- Log validation errors and provide suggestions for common mistakes.

5. **Schema Evolution and Versioning**:

- Implement a versioning system for the configuration schema to manage changes over time.
- Develop a process for deprecating old schema versions and supporting backward compatibility.

6. **Community Involvement**:

- Encourage community contributions to the configuration schema and validation logic.
- Set up a feedback mechanism to gather input from users on configuration challenges and improvements.
