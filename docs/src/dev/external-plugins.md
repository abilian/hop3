# External Plugin Guide

This guide covers how to create, package, distribute, and maintain external Hop3 plugins as separate Python packages.

## Overview

External plugins allow third-party developers to extend Hop3 without modifying the core codebase. They are:

- **Distributed separately** via PyPI or other package repositories
- **Installed independently** using pip/uv
- **Auto-discovered** via setuptools entry points
- **Versioned independently** from Hop3 core

## When to Create an External Plugin

Create an external plugin when:

- You want to share a plugin with the community
- The plugin is specific to your organization's needs
- The plugin adds support for proprietary/commercial software
- You want independent versioning and release cycles
- The plugin has different dependencies than Hop3 core

Keep plugins internal when:

- They're part of Hop3's core functionality
- They're widely used across all installations
- They have no extra dependencies

## Quick Start

### 1. Project Structure

Create a new Python project:

```
my-hop3-plugin/
├── pyproject.toml          # Package metadata and build config
├── README.md                # Plugin documentation
├── LICENSE                  # License file (Apache 2.0 recommended)
├── src/
│   └── my_hop3_plugin/
│       ├── __init__.py      # Package initialization
│       ├── plugin.py        # Plugin class with hooks
│       ├── builder.py       # Strategy implementations
│       └── deployer.py
└── tests/
    ├── __init__.py
    ├── test_plugin.py       # Plugin tests
    └── test_builder.py
```

### 2. pyproject.toml

Configure your package with entry points:

```toml
[project]
name = "my-hop3-plugin"
version = "0.1.0"
description = "My custom Hop3 plugin"
authors = [
    {name = "Your Name", email = "you@example.com"}
]
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "hop3-server>=0.2.0",
]
license = {text = "Apache-2.0"}

[project.urls]
Homepage = "https://github.com/yourusername/my-hop3-plugin"
Repository = "https://github.com/yourusername/my-hop3-plugin"
Issues = "https://github.com/yourusername/my-hop3-plugin/issues"

# Entry point for plugin discovery
[project.entry-points."hop3.plugins"]
my_plugin = "my_hop3_plugin.plugin:plugin"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/my_hop3_plugin"]
```

### 3. Plugin Implementation

Implement your plugin in `src/my_hop3_plugin/plugin.py`:

```python
# Copyright (c) 2025, Your Organization
#
# SPDX-License-Identifier: Apache-2.0

"""My Hop3 Plugin."""

from __future__ import annotations

from hop3.core.hooks import hookimpl
from .builder import MyBuilder
from .deployer import MyDeployer

class MyPlugin:
    """Custom plugin for MyFramework support."""

    name = "my_plugin"

    @hookimpl
    def get_builders(self) -> list:
        """Provide MyFramework build strategy."""
        return [MyBuilder]

    @hookimpl
    def get_deployment_strategies(self) -> list:
        """Provide MyFramework deployment strategy."""
        return [MyDeployer]

# Auto-register plugin instance
plugin = MyPlugin()
```

### 4. Package Initialization

Export the plugin in `src/my_hop3_plugin/__init__.py`:

```python
"""My Hop3 Plugin package."""

from .plugin import plugin

__version__ = "0.1.0"
__all__ = ["plugin"]
```

### 5. Strategy Implementations

Implement your strategies (example: `src/my_hop3_plugin/builder.py`):

```python
# Copyright (c) 2025, Your Organization
#
# SPDX-License-Identifier: Apache-2.0

"""MyFramework build strategy."""

from __future__ import annotations

import subprocess
from pathlib import Path

from hop3.core.protocols import Builder, BuildArtifact, DeploymentContext
from hop3.lib import log, Abort


class MyBuilder:
    """Build strategy for MyFramework applications."""

    name = "myframework"

    def __init__(self, context: DeploymentContext):
        self.context = context

    def accept(self) -> bool:
        """Accept if myframework.yaml exists."""
        return (self.context.source_path / "myframework.yaml").exists()

    def build(self) -> BuildArtifact:
        """Build MyFramework application."""
        log("Building MyFramework application...", fg="blue")

        # Your build logic here
        venv_path = self._create_environment()
        self._install_dependencies(venv_path)

        log("Build complete", fg="green")

        return BuildArtifact(
            kind="myframework",
            location=str(venv_path),
            metadata={"framework_version": "1.0"}
        )

    def _create_environment(self) -> Path:
        # Implementation details
        pass

    def _install_dependencies(self, venv_path: Path):
        # Implementation details
        pass
```

## Building and Testing

### Local Development

Install your plugin in development mode:

```bash
# From plugin directory
pip install -e .

# Or with uv
uv pip install -e .
```

This allows you to test the plugin while developing without reinstalling.

### Running Tests

```bash
# Using pytest
pytest tests/

# With coverage
pytest --cov=my_hop3_plugin tests/
```

### Testing with Hop3

Test your plugin with a real Hop3 installation:

```bash
# Install hop3-server and your plugin
pip install hop3-server
pip install -e .

# Verify plugin is discovered
python -c "from hop3.core.plugins import get_plugin_manager; pm = get_plugin_manager(); print([p for p in pm.list_name_plugin()])"

# Test deployment with your plugin
hop deploy myapp
```

## Packaging and Distribution

### Building Distributions

Build wheel and source distributions:

```bash
# Using build
python -m build

# Or with hatch
hatch build

# Or with uv
uv build
```

This creates:
- `dist/my_hop3_plugin-0.1.0-py3-none-any.whl` (wheel)
- `dist/my_hop3_plugin-0.1.0.tar.gz` (source distribution)

### Publishing to PyPI

#### Test PyPI (recommended first)

```bash
# Install twine
pip install twine

# Upload to Test PyPI
twine upload --repository testpypi dist/*

# Test installation
pip install --index-url https://test.pypi.org/simple/ my-hop3-plugin
```

#### Production PyPI

```bash
# Upload to PyPI
twine upload dist/*

# Users can now install
pip install my-hop3-plugin
```

### GitHub Releases

Create a release on GitHub with the distribution files:

1. Tag your release: `git tag v0.1.0`
2. Push the tag: `git push --tags`
3. Create GitHub release from tag
4. Upload `dist/*.whl` and `dist/*.tar.gz` to release assets

## Versioning

### Semantic Versioning

Follow [SemVer](https://semver.org/):

- **MAJOR**: Incompatible API changes (2.0.0)
- **MINOR**: Backwards-compatible functionality (1.1.0)
- **PATCH**: Backwards-compatible bug fixes (1.0.1)

### Version Compatibility

Specify Hop3 compatibility in `pyproject.toml`:

```toml
dependencies = [
    "hop3-server>=0.2.0,<0.3.0",  # Compatible with 0.2.x
]
```

### Changelog

Maintain a `CHANGELOG.md`:

```markdown
# Changelog

## [0.2.0] - 2025-02-01

### Added
- Support for MyFramework 2.0
- New `scale()` implementation

### Fixed
- Bug in dependency resolution

## [0.1.0] - 2025-01-15

### Added
- Initial release
- Basic MyFramework build support
```

## Documentation

### README.md

Your README should include:

```markdown
# My Hop3 Plugin

Description of what your plugin does.

## Installation

```bash
pip install my-hop3-plugin
```

## Usage

Deploy a MyFramework application:

```bash
hop deploy myapp
```

The plugin will automatically detect MyFramework applications via `myframework.yaml`.

## Configuration

Set environment variables in `hop3.toml`:

```toml
[env]
MYFRAMEWORK_VERSION = "2.0"
```

## Supported Versions

- Hop3: >= 0.2.0
- MyFramework: >= 1.0

## License

Apache 2.0
```

### API Documentation

Document your public APIs:

```python
class MyBuilder:
    """Build strategy for MyFramework applications.

    This builder detects MyFramework applications by looking for a
    `myframework.yaml` configuration file in the application root.

    Attributes:
        name: Strategy name ("myframework")
        context: Deployment context

    Example:
        The builder is automatically used when deploying an app with
        myframework.yaml:

        ```yaml
        # myframework.yaml
        version: "1.0"
        runtime: myframework
        ```
    """
```

## Testing Against Multiple Hop3 Versions

### Using tox

Create `tox.ini`:

```ini
[tox]
envlist = py311-hop3{020,021,022}

[testenv]
deps =
    pytest
    pytest-cov
    hop3020: hop3-server>=0.2.0,<0.2.1
    hop3021: hop3-server>=0.2.1,<0.2.2
    hop3022: hop3-server>=0.2.2,<0.2.3
commands =
    pytest tests/
```

Run tests:

```bash
tox
```

### Using GitHub Actions

Create `.github/workflows/test.yml`:

```yaml
name: Test

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
        hop3-version: ["0.2.0", "0.2.1", "0.2.2"]

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          pip install hop3-server==${{ matrix.hop3-version }}
          pip install -e .[dev]

      - name: Run tests
        run: pytest tests/
```

## Maintenance

### Keeping Up with Hop3

Monitor Hop3 releases:

1. Watch the [Hop3 repository](https://github.com/abilian/hop3)
2. Subscribe to release notifications
3. Test your plugin against new versions
4. Update compatibility declarations

### Deprecation Handling

If Hop3 deprecates an API you use:

1. Test against new Hop3 version
2. Update to new API
3. Bump minimum Hop3 version if needed
4. Release new plugin version

Example:

```python
# Old (deprecated)
from hop3.core.runtime_registry import get_deployment_strategy
strategy = get_deployment_strategy(app)

# New
from hop3.core.plugins import get_deployment_strategy_by_name
strategy = get_deployment_strategy_by_name(app, app.runtime)
```

### Security Updates

If your plugin has security issues:

1. Fix the vulnerability
2. Release a patch version
3. Create a GitHub security advisory
4. Notify users via release notes

## Examples

### Minimal Plugin

The simplest possible external plugin:

```python
# src/simple_plugin/plugin.py
from hop3.core.hooks import hookimpl
from hop3.builders.python import PythonBuilder

class SimplePlugin:
    """Minimal plugin example."""
    name = "simple"

    @hookimpl
    def get_builders(self) -> list:
        # Just re-export existing builder with custom name
        return [PythonBuilder]

plugin = SimplePlugin()
```

### Service Plugin

A plugin that adds a new service:

```python
# src/mysql_plugin/plugin.py
from hop3.core.hooks import hookimpl
from .mysql_service import MySQLService

class MySQLPlugin:
    """MySQL database service plugin."""
    name = "mysql"

    @hookimpl
    def get_addons(self) -> list:
        return [MySQLService]

plugin = MySQLPlugin()
```

```toml
# pyproject.toml
[project]
name = "hop3-mysql"
version = "0.1.0"
dependencies = [
    "hop3-server>=0.2.0",
    "pymysql>=1.0.0",  # Plugin-specific dependency
]

[project.entry-points."hop3.plugins"]
mysql = "mysql_plugin.plugin:plugin"
```

### Multi-Strategy Plugin

A comprehensive plugin with multiple strategies:

```python
# src/myframework_plugin/plugin.py
from hop3.core.hooks import hookimpl
from .builder import MyFrameworkBuilder
from .deployer import MyFrameworkDeployer
from .service import MyFrameworkCache

class MyFrameworkPlugin:
    """Complete MyFramework integration."""
    name = "myframework"

    @hookimpl
    def get_builders(self) -> list:
        return [MyFrameworkBuilder]

    @hookimpl
    def get_deployment_strategies(self) -> list:
        return [MyFrameworkDeployer]

    @hookimpl
    def get_addons(self) -> list:
        return [MyFrameworkCache]

plugin = MyFrameworkPlugin()
```

## Best Practices

### 1. Clear Naming

- Package name: `hop3-{feature}` (e.g., `hop3-mysql`, `hop3-nodejs`)
- Plugin name attribute: descriptive and unique
- Strategy names: match ecosystem conventions

### 2. Minimal Dependencies

- Only depend on what you actually use
- Specify version ranges conservatively
- Don't pin exact versions in libraries

```toml
# Good
dependencies = [
    "hop3-server>=0.2.0,<0.3.0",
    "pymysql>=1.0.0",
]

# Bad - too restrictive
dependencies = [
    "hop3-server==0.2.0",  # Blocks updates
    "pymysql==1.0.3",      # Exact pin
]
```

### 3. Comprehensive Tests

- Test plugin discovery
- Test strategy registration
- Test actual functionality
- Test error handling

### 4. Clear Documentation

- Installation instructions
- Configuration options
- Examples
- Troubleshooting guide

### 5. Licensing

Use a permissive license compatible with Hop3:

- Apache 2.0 (recommended, same as Hop3)
- MIT
- BSD

### 6. Type Hints

Use type hints for better IDE support:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hop3.core.protocols import DeploymentContext, BuildArtifact

class MyBuilder:
    def __init__(self, context: DeploymentContext) -> None:
        self.context = context

    def build(self) -> BuildArtifact:
        ...
```

## Common Issues

### Plugin Not Discovered

**Problem**: Plugin is installed but not found by Hop3.

**Solutions**:
1. Check entry point configuration in `pyproject.toml`
2. Verify plugin instance is created: `plugin = MyPlugin()`
3. Check import in `__init__.py`
4. Reinstall plugin: `pip install -e .`

### Version Conflicts

**Problem**: Plugin and Hop3 have incompatible dependencies.

**Solutions**:
1. Widen version ranges in dependencies
2. Test against multiple Hop3 versions
3. Update plugin to use current Hop3 APIs

### Import Errors

**Problem**: `ImportError` when loading plugin.

**Solutions**:
1. Ensure all dependencies are installed
2. Check Python version compatibility
3. Verify package structure matches entry point

## See Also

- [Plugin Development Guide](plugin-development.md) - How to create plugins
- [Protocol Reference](protocol-reference.md) - Strategy interfaces
- [Hook Specifications](hook-specifications.md) - Available hooks
- [Packaging Python Projects](https://packaging.python.org/tutorials/packaging-projects/) - Python packaging guide
- [Setuptools Entry Points](https://setuptools.pypa.io/en/latest/userguide/entry_point.html) - Entry point documentation
