---
date: 2026-03-17
template: blog_post.html
description: How we validate hop3.toml and provide helpful error messages.
tags:
  - Engineering
  - Configuration
---

# Configuration Validation with Pydantic

A single typo in a configuration file can cause hours of debugging. We learned this the hard way when users reported deployment failures with helpful messages like "502 Bad Gateway." The root cause? `post-deploy` instead of `before-run` in their `hop3.toml`.

## The Problem

Hop3 uses `hop3.toml` for application configuration:

```toml
[metadata]
id = "myapp"

[build]
toolchain = "python"

[run]
start = "gunicorn app:app"
post-deploy = "python manage.py migrate"  # TYPO!
```

The problem: `post-deploy` isn't a valid field. The correct field is `before-run`. But without validation, Hop3 silently ignores the typo, and the migration never runs. The app deploys successfully, but then crashes because the database schema is wrong.

## The Solution: Pydantic Schema

We added strict validation using Pydantic models with `extra="forbid"`:

```python
from pydantic import BaseModel, ConfigDict, Field

class RunSection(BaseModel):
    """[run] section - Runtime configuration."""

    model_config = ConfigDict(extra="forbid")  # Reject unknown fields!

    start: str | list[str] | None = Field(
        default=None,
        description="Start command for the web process",
    )
    before_run: str | list[str] | None = Field(
        default=None,
        alias="before-run",
        description="Commands to run before starting the app",
    )
    workers: dict[str, str] | None = Field(
        default=None,
        description="Named worker processes",
    )
    # ... other valid fields
```

Now when you use an invalid field:

```toml
[run]
start = "gunicorn app:app"
post-deploy = "python manage.py migrate"
```

You get a clear error:

```
ERROR: hop3.toml validation failed
  Invalid hop3.toml configuration:
    - Unknown field 'post-deploy'
      Did you mean 'before-run'?

  Hint: Check the hop3.toml reference for valid fields:
    https://hop3.cloud/reference/config/
```

## The Full Schema

We model every section of `hop3.toml`:

```python
class Hop3TomlSchema(BaseModel):
    """Complete hop3.toml schema with validation."""

    model_config = ConfigDict(
        extra="forbid",  # Reject unknown sections
        populate_by_name=True,  # Allow aliases
    )

    metadata: MetadataSection | None = None
    build: BuildSection | None = None
    run: RunSection | None = None
    env: dict[str, Any] | None = None
    static: dict[str, str] | None = None
    healthcheck: HealthcheckSection | None = None
    backup: BackupSection | None = None
    addons: list[AddonConfig] | None = None
```

Each section has its own model with specific field definitions.

## Helpful Error Messages

We transform Pydantic's technical errors into user-friendly messages:

```python
class Hop3TomlValidationError(Exception):
    def _format_message(self) -> str:
        lines = ["Invalid hop3.toml configuration:"]

        for error in self.errors:
            loc = " -> ".join(str(x) for x in error.get("loc", []))
            error_type = error.get("type", "")

            if error_type == "extra_forbidden":
                lines.append(f"  - Unknown field '{loc}'")
                lines.append("    Did you mean one of the valid options?")
            else:
                msg = error.get("msg", "Unknown error")
                lines.append(f"  - {loc}: {msg}")

        lines.append("")
        lines.append("Hint: Check the hop3.toml reference:")
        lines.append("  https://hop3.cloud/reference/config/")

        return "\n".join(lines)
```

## Example Error Messages

### Unknown Field

```toml
[build]
toolchain = "python"
post_build = "npm run build"  # Should be after-build
```

```
Invalid hop3.toml configuration:
  - Unknown field 'post_build'
    Did you mean 'after-build'?
```

### Wrong Type

```toml
[run]
start = 123  # Should be a string
```

```
Invalid hop3.toml configuration:
  - run -> start: Input should be a valid string
```

### Invalid Value

```toml
[build]
builder = "kubernetes"  # Not a valid builder
```

```
Invalid hop3.toml configuration:
  - build -> builder: Invalid builder 'kubernetes'.
    Must be one of: auto, local, docker
```

## JSON Schema Export

Pydantic can generate JSON Schema, which enables IDE autocompletion:

```python
def get_json_schema() -> dict[str, Any]:
    """Generate JSON Schema for hop3.toml."""
    return Hop3TomlSchema.model_json_schema()
```

VS Code with the Even Better TOML extension can use this for:
- Field autocompletion
- Inline documentation
- Real-time validation

## Validation at Deploy Time

Validation happens early in the deployment process:

```python
def deploy_app(app_name: str, source_path: Path) -> None:
    # Load and validate hop3.toml first
    config_path = source_path / "hop3.toml"
    if config_path.exists():
        data = tomllib.loads(config_path.read_text())
        try:
            validate_hop3_toml(data)
        except Hop3TomlValidationError as e:
            log(f"hop3.toml validation failed: {config_path}")
            log(e.message)
            raise DeploymentError(e.message)

    # Continue with deployment...
```

This catches configuration errors before any work is done.

## Aliases for Flexibility

TOML uses dashes in keys, but Python uses underscores. We support both:

```python
class BuildSection(BaseModel):
    before_build: str | list[str] | None = Field(
        default=None,
        alias="before-build",  # TOML uses dashes
    )
```

Both work:

```toml
# This works
[build]
before-build = "npm install"

# This also works
[build]
before_build = "npm install"
```

## Lessons Learned

### 1. Fail Early, Fail Clearly

The worst bugs are silent failures. `extra="forbid"` turns silent ignores into clear errors.

### 2. Context in Error Messages

Generic errors like "validation failed" aren't helpful. Include:
- What field was wrong
- What was expected
- Where to find documentation

### 3. Support Common Patterns

Users expect both `before-build` and `before_build` to work. Using Pydantic aliases, we can support both without ambiguity.

### 4. Don't Over-Validate

Some sections need flexibility. Environment variables can have any keys:

```python
class Hop3TomlSchema(BaseModel):
    env: dict[str, Any] | None = None  # No extra="forbid" here
```

## Try It

Create an invalid `hop3.toml` and try to deploy:

```toml
[metadata]
id = "test"

[run]
strat = "python app.py"  # Typo: should be "start"
```

```bash
hop3 deploy test
```

You'll get a clear error message pointing to the problem.

---

*For the complete hop3.toml reference, see [Designing hop3.toml](2026-02-hop3-toml-reference.md) or the [Configuration Reference](/reference/config/) documentation.*
