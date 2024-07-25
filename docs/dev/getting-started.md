# Getting Started

Before you start, it's important to familiarize yourself with Hop3's core values and objectives. Please take a moment to read the [core values of Hop3](../README.md#core-values) outlined in our README. Understanding these principles will help you make meaningful contributions that align with the project's goals.

## Installation

The project uses `poetry` for dependency management. However, since it is structured as a monorepo, you will need to install the dependencies for each package separately. To install the dependencies for a specific package, navigate to the package directory and run the following command:

```bash
poetry install
```

## Tooling

The projects uses several tools to ensure code quality and consistency. These tools are configured in the `pyproject.toml` file, the `setup.cfg` file, and tool-specific files like `ruff.toml` for Ruff.

### Main tools

We're using the following tools. These are pretty much standard in the Python ecosystem:

- **ruff**: Linter and all-purpose tool
- **black**: Code formatter
- **isort**: Import sorter
- **flake8**: Linter
- **mypy**: Static type checker
- **bandit**: Security linter
- **safety**: Software supply chain checker
- **poetry**: Dependency management
- **invoke**: Task runner
- **make**: Task runner
- **pre-commit**: Git hooks
- **pytest**: Testing framework
- **nox**: Testing automation
- **mkdocs**: Documentation generator
- **mkdocs-material**: Documentation theme

Additionally, we use the following tools for specific tasks:

- **uv**: Virtual environment manager
- **fish**: Shell (optional, but some Makefile commands depende on it)

### Running Tools

We use two task runners to run the tools: `make` and `inv`.

Typing `make help` and `inv -l` will show you the available commands.

Why both? Because `make` is more common and `inv` is more powerful. We use `make` for common tasks and `inv` for more complex ones, specially those that need to be executed in all subprojects (due to the monorepo nature of the project).
