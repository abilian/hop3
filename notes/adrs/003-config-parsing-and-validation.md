## ADR: Config Parsing and Validation

### Status

Status: Draft (v0.1)

### Context

We have decided, early on in the project, to use an existing syntax (instead of creating a new DSL) for the `hop3.toml` files, which are the heart of the Hop3 platform.

We chose to favor [TOML](https://toml.io/en/) for several reasons, including:

1. **Simplicity and Readability**: TOML was designed to be simple and easy to understand for humans, making it great for configuration files. It aims to be more readable and straightforward than YAML or JSON, which can become complex and verbose with large data structures.
2. **Explicit and Obvious**: TOML is designed to map unambiguously to a hash table. It aims to be more explicit and less prone to errors or misinterpretation than YAML, which has more complex features like references and tags.
3. **Consistent Style**: TOML has a more consistent style, whereas YAML can be written in different ways (flow style and block style) which might cause confusion.
4. **Strong Typing**: TOML has a clear type system, including explicit types for dates and times, which JSON lacks. While YAML also supports data types, its type system can sometimes lead to surprising results due to its reliance on tags.

However, we also choose to support JSON and YAML as alternatives because the concrete syntax of the `hop3.toml` files is mostly irrelevant, as long as it produces a valid JSON object.

### Decision

- Parse the configuration once (and report errors as soon as possible), apply some transformations, and transform it into JSON which will then be the reference file (loaded by `jsonlib` when necessary, but without any further transformations, or as little as possible).
- Use Pydantic to validate the `hop3.toml` file.
- Add specific code to validate the "env" section (because we don't know the keywords a priori), and possibly other sections.

### Alternatives

- Status quo (ad-hoc class with `@properties` that can provide)

### Consequences

#### Benefits

- **Better Developer Experience (DX)**: Early feedback to developers or package-builders about invalid configuration syntax or basic semantics will lead to a better developer experience.
- **Fewer Runtime Dependencies**: The build-time/runtime on TOML or YAML parsers is avoided.
- **Easier Evolution**: The configuration format can evolve more easily as it is defined and validated through a consistent schema.

### Action Items

- Converge the configuration format to something consistent between all the examples that are currently available:
  - Make the schema as described with Pydantic consistent with the schema described (or specified) in the documentation.
  - Make the schema consistent with the existing configuration files.

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
