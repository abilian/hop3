# Getting Started

Before you start, it's important to familiarize yourself with Hop3's core values and objectives. Please take a moment to read the [core values of Hop3](../README.md#core-values) outlined in our README. Understanding these principles will help you make meaningful contributions that align with the project's goals.

## Development Environment

### Using `uv` and `poetry`

`uv` and `poetry` should be installed on your system. We'll get rif of poetry soon but we're not there yet.

The easiest way to create a development environment is to use the following:

```bash
make develop
. venv/bin/activate # (or activate.fish for fish shell)
```

This creates a virtual environment in `.env` using `uv` and installs the dependencies using `poetry`.

### Using only `poetry`

At the moment, it should still be possible to use only `poetry` to create a development environment. To do so, run the following command:

```bash
poetry shell
poetry install
inv install
```

### Using Nix

If you are using Nix, you can use the provided `shell.nix` file to create a development environment. To do so, run the following command:

```bash
nix-shell
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
