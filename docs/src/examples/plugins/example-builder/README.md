# Example Builder Plugin

This is a minimal example of a Hop3 build strategy plugin. It demonstrates the core concepts of plugin development.

## What This Plugin Does

This plugin provides a simple build strategy that creates a Python virtualenv for applications. It's similar to the built-in Python builder but simplified for educational purposes.

## Files

- `plugin.py` - Plugin class with hook implementation
- `builder.py` - Build strategy implementation
- `README.md` - This file

## How It Works

1. **Plugin Registration**: The `ExamplePlugin` class implements the `get_build_strategies()` hook
2. **Detection**: The builder checks for `requirements.txt` to detect Python apps
3. **Build Process**: Creates a virtualenv and installs dependencies
4. **Artifact**: Returns information about the created virtualenv

## Using This Example

### As a Learning Tool

Study the code to understand:
- How to structure a plugin
- How to implement the `BuildStrategy` protocol
- How to register strategies via hooks
- How to return build artifacts

### As a Template

Copy this structure for your own build strategy:

1. Copy the directory
2. Rename files and classes
3. Modify `accept()` to detect your app type
4. Implement your build logic in `build()`
5. Update the plugin registration

## Key Concepts Demonstrated

### Protocol Implementation

The `ExampleBuilder` class implements the `BuildStrategy` protocol:

```python
class BuildStrategy(Protocol):
    name: str
    context: DeploymentContext

    def accept(self) -> bool: ...
    def build(self) -> BuildArtifact: ...
```

### Hook Implementation

The plugin uses `@hookimpl` to implement hooks:

```python
@hookimpl
def get_build_strategies(self) -> list:
    return [ExampleBuilder]
```

### Error Handling

Uses `Abort` from `hop3.lib` for user-facing errors:

```python
from hop3.lib import Abort

raise Abort("Build failed: requirements.txt not found")
```

### Logging

Uses `log()` from `hop3.lib` for user feedback:

```python
from hop3.lib import log

log("Building Python application...", fg="blue")
```

## Testing

To test this plugin:

```python
from pathlib import Path
from hop3.core.protocols import DeploymentContext
from builder import ExampleBuilder

# Create test context
context = DeploymentContext(
    app_name="test",
    source_path=Path("/path/to/app"),
    app_config={}
)

# Instantiate builder
builder = ExampleBuilder(context)

# Test detection
assert builder.accept() is True

# Test build
artifact = builder.build()
assert artifact.kind == "virtualenv"
```

## Next Steps

- See [plugin-development.md](../../../dev/plugin-development.md) for comprehensive guide
- See [protocol-reference.md](../../../dev/protocol-reference.md) for protocol details
- Check real-world example: `hop3/builders/python.py`
