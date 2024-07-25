# ADR: Detailed `hop3.toml` Format

## Status

Status: Draft

Revisions:
- v0.2: Update according to new template (2024-07-25)
- v0.1: Initial draft (2024-07-17)

## Summary

This ADR details the format and structure of the `hop3.toml` file, the primary configuration file for the Hop3 platform. Designed for simplicity, human readability, and explicitness, the `hop3.toml` format also supports YAML and JSON configurations. This document specifies the sections and fields within `hop3.toml` and their intended use.

## Context and Goals

The `hop3.toml` file is central to the Hop3 platform, serving as the primary configuration file for deploying and managing web applications. Its design aims to be simple, human-readable, and explicit. The configuration can also be written in YAML and JSON formats. This document describes the detailed format and structure of the `hop3.toml` file, which contains a limited set of metadata and configuration details necessary for the operation of the Hop3 platform.

## Decision

The `hop3.toml` file will be used as the primary configuration format for the Hop3 platform. The file structure includes several sections, some mandatory and others optional, to cover various aspects of application deployment and management. Each section has specific fields that provide the necessary metadata and configuration details.

## Consequences

### Benefits

- **Simplicity**: A structured and clear format that is easy to understand and use.
- **Flexibility**: Supports multiple formats (TOML, YAML, JSON) to cater to user preferences.
- **Comprehensiveness**: Covers all necessary aspects of configuration and metadata for application deployment.

### Drawbacks

- **Learning Curve**: New users might need some time to get accustomed to the detailed structure.
- **Maintenance**: Keeping the format and parsing logic consistent across different formats might require additional effort.

## Action Items

1. **Develop Detailed Documentation**:
    - Create comprehensive documentation outlining each section and field within the `hop3.toml` file.
    - Provide examples and best practices to guide users.

2. **Implement Parsing Logic**:
    - Develop robust parsing logic to handle TOML, YAML, and JSON formats.
    - Ensure the consistency and correctness of parsed data.

3. **Validation Framework**:
    - Use Pydantic or similar tools for schema validation to ensure data integrity.
    - Implement format-specific validation where necessary.

4. **Tooling and Support**:
    - Develop CLI tools to assist users in generating and validating `hop3.toml` files.
    - Integrate validation into the CI/CD pipeline to catch errors early.

5. **Community Engagement**:
    - Gather feedback from users to improve the configuration format.
    - Update the format and documentation based on user input and evolving needs.

## Alternatives

- **Single Format**: Using only `hop3.toml` format to simplify implementation but at the cost of flexibility.
- **Ad-hoc Methods**: Using unstructured or ad-hoc configuration methods, leading to potential inconsistencies and complexity.

## Related

- ADR #002: Detailed `hop3.toml` Format
- ADR #003: Config Parsing and Validation

## References

- TOML documentation: https://toml.io/en/
- YAML documentation: https://yaml.org/
- JSON documentation: https://www.json.org/

## The Specifications

The `hop3.toml` file contains several sections, mandatory or optional. Their order is not fixed, although a logical order is recommended.

### `[metadata]`

- **Mandatory**
- Contains information that describes the application. Metadata is used as a basis for naming images, services, and providers.

### `[build]`

- **Optional**
- Specifies the environment and specific actions to be performed to build the executable artifact(s) of the application.

### `[run]`

- **Optional**
- Contains actions to perform to start the application.

### `[env]`

- **Optional**
- Environment variables, static or dynamic. The variables can be replaced by new values at runtime.

### `[port]`

- **Optional**. However, the current implementation issues a warning if no public port is declared.
- Dictionary of named ports (e.g., `[port.web]`) used by the application.

### `[healthcheck]`

- **Optional**
- Healthcheck options for the application.

### `[backup]`

- **Optional**
- Parameters for the backup of the application.

### `[[provider]]`

- **Optional**
- List of services required by the application.

---

### Section `[metadata]`

Notes:

- If not specified, the type of the value is String with no length limitation.
- Strings are Python `f-string`: use of `{}` to reference other Metadata (such as version) is possible.
- Keys containing a '-' can also be written with a '_'.

#### `id`

- **Mandatory**
- Identifier of the package. Should be unique in the managed area.
- Example: `id = "hedgedoc"`

#### `version`

- **Mandatory**
- Version of the packaged application.
- Example: `version = "1.9.7"`

#### `title`

- **Mandatory**
- Short title of the package.
- Example: `title = "HedgeDoc"`

#### `author`

- **Mandatory**
- Author of the packaged application.
- Example: `author = "HedgeDoc authors"`

#### `description`

- **Optional**
- Long description of the application.
- Example: `description = "The best platform to write and share markdown"`

#### `tagline`

- **Optional**
- Short description of the application.
- Example: `tagline = "The best platform to write and share markdown"`

#### `website`

- **Optional**
- String containing a valid URL.
- Reference website of the application.
- Example: `website = "https://hedgedoc.org/"`

#### `tags`

- **Optional**
- List of strings describing the application.
- Example: `tags = ["Markdown", "Documentation", "Collaboration"]`

#### `profile`

- **Optional**
- Usage profile (WIP).

#### `release`

- **Optional**
- Integer.
- Release number of this `hop3.toml` file.
- Example: `release = 1`

---

### Section `[build]`

Notes:

- If not specified, the type of the value is String with no length limitation.
- All fields are optional except the `license` field.

#### `license`

- **Mandatory**
- License of the packaged application.
- Example: `license = "AGPL-3.0 license"`

#### `src-url`

- **Optional**
- String containing a valid URL of the source code.
- Example: `src-url = "https://github.com/hedgedoc/hedgedoc/releases/download/{version}/hedgedoc-{version}.tar.gz"`

#### `src-checksum`

- **Optional**
- SHA256 checksum to enforce upon the downloaded source code.
- Example: `src-checksum = 'c9bd99c65cf45fa1d7808855b46abbfa13b24400254d8da5e81dae2965494bb3'`

#### `git-url`

- **Optional**
- String containing a valid URL of the git repository.
- Example: `git-url = "https://github.com/jech/galene.git"`

#### `git-branch`

- **Optional**
- Branch to check out from the git repository.
- Example: `git-branch = "galene-0.6-branch"`

#### `base-image`

- **Optional**
- String containing a valid reference to a base image if applicable.
- Example: `base-image = "ubuntu:20.04"`

#### `method`

- **Optional**
- Force selection of the build method, possible values are `build` or `wrap`.
- Example: `method = "wrap"`

#### `builder`

- **Optional**
- Reference of a specific build environment.
- Example: `builder = "node-16"`
- Example (alternate syntax): `builder = {name = "ruby", version = "3.2"}`

#### `builders`

- **Optional**
- List of builder environments (WIP, experimental).

#### `packages`

- **Optional**
- List of system packages to install for the build step.
- Example: `packages = ["build-essential"]`

#### `meta-packages`

- **Optional**
- Group of packages defined by Hop3 to facilitate some installation.
- Example: `meta-packages = ["postgres-client"]`

#### `build`

- **Optional**
- List of shell commands to be executed during the build process.
- Example:

```
build = [
    "CGO_ENABLED=0 go build -ldflags='-s -w'",
    "cp galene /hop3/app",
    "cp LICENCE /hop3/app",
    "cp -a static /hop3/app",
    "mkdir /hop3/app/groups",
    "mkdir /hop3/app/data"
]
```

#### `test`

- **Optional**
- List of shell commands for "smoke test" to check that the installation was successful.
- Example: `test = "python -c 'import flask_show'"`

#### `before-build`

- **Optional**
- List of shell commands to be executed before the actual build command.

#### `pip-install`

- **Optional**
- List of Python packages to install with the `pip` command.
- Example: `pip-install = ["*.whl"]`
- Example: `pip-install = ["flask", "gunicorn"]`

#### `project`

- **Optional**
- Relative path of the project to build from the downloaded source code.
- Example: `project = "./alternate/src"`

---

### Section `[run]`

Notes:

- If not specified, the type of the value is String with no length limitation.
- All fields are optional.
- All command strings can use shell expansion to access ENV variables available in the run context.

#### `packages`

- **Optional**
- List of system packages required by the application.
- Example: `packages = ["fontconfig", "fonts-noto"]`

#### `before-run`

- **Optional**
- List of shell commands to be executed before the actual run command.

#### `start`

- **Optional**
- List of shell commands to start the application.
- Example: `start = "bundle exec rails s"`
- Example: `start = "yarn start"`
- Example:

```
start = [
    "init-db",
    "gunicorn --workers 2 -b :5000 flask_app.app:app"
]
```

---

### Section `[env]`

Each field is a variable declaration. Format can be:

- A Python `f-string`.
- A dict using a `from`/`key` syntax to access other values of the running environment.
- A dict using specific parameters for special functions like generating a password.

#### Examples:

- Simple values:

```
[env]
NODE_ENV = "production"
DEBUG = "true"
UPLOADS_MODE = "0700"
TZ = "Europe/Paris"
```

- Copy information from a service declared in the `provider` section with name `database`:

```
DB_HOST = { from="database", key="hostname" }
DB_PORT = { from="database", key="POSTGRES_PORT" }
DB_NAME = { from="database", key="POSTGRES_DB" }
DB_USERNAME = { from="database", key="POSTGRES_USER" }
DB_PASSWORD = { from="database", key="POSTGRES_PASSWORD" }
```

- Copy the value of the app `domain` (fqdn) to the application at start time:

```
CMD_DOMAIN = { from="", key="domain" }
CMD_ALLOW_ORIGIN = { key="domain" }
```

- Generate a password:

```
GALENE_ADM_PWD = { random='true', length=24 }
ACKEE_PASSWORD = { random='true', length=16, display='true' }
```

- Complex string using `f-string` evaluation:

```
DB_HOST = { from="database", key="hostname" }
DB_USER = { from="database", key="MONGO_INITDB_ROOT_USERNAME" }
DB_PWD = { from="database", key="MONGO_INITDB_ROOT_PASSWORD" }
DB_PORT = 27017
ACKEE_MONGODB = "mongodb://{DB_USER}:{DB_PWD}@{DB_HOST}:{DB_PORT}/"
```

- Access to the detected external IP of the host (public IP):

```
MY_IP = { external_ip='true' }
```

---

### Section `[port]`

- **Optional**
- However, the current implementation issues a warning if no public port is declared.
- Dictionary of named ports (e.g., `[port.web]`) used by the application.

---

### Section `[healthcheck]`

Currently, the `healthcheck` section defines commands and parameters to check the health of the application.

#### Example:

```
[healthcheck]
command = "node /hop3/build/hedgedoc/healthcheck.mjs"
interval = 10
```

---

### Section `[backup]`

- **Work in progress**
- Current keys: `method`, `frequency`, `options`.

---

### Section `[[provider]]`

A provider is another service required by the main application. Several providers can be declared.

Providers are identified by a `name` that permits reference to the provider in the `[env]` section.

#### Examples:

- Postgres database:

```
[[provider]]
name = "database"
type = "postgres"
version = ">=14, <15"
[provider.backup]
method = "pg_dumpall"
destination = "local"
frequency = "24h"
```

- MongoDB database:

```
[[provider]]
name = "database"
type = "mongo"
version = ">=5, <6"
```

- Redis database (cache configuration):

```
[[provider]]
name = "database"
type = "redis-cache"
version = ">=7"
```
