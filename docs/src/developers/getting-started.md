# Getting Started

Before you start, it's important to familiarize yourself with Hop3's core values and objectives. Please take a moment to read the [core values of Hop3](core-values.md) document. Understanding these principles will help you make meaningful contributions that align with the project's goals.

## Development Environment

### Using `uv`

[`uv`](https://docs.astral.sh/uv/) should be installed on your system. It is the only package manager used by Hop3.

The easiest way to create a development environment is:

```bash
make develop
```

This installs the project's dependencies with `uv sync`, activates the `pre-commit` hooks, and configures a few local git defaults. `uv` manages the virtual environment under `.venv/`; prefix commands with `uv run` (for example `uv run pytest`) to run them inside it.

You can also install the dependencies directly:

```bash
uv sync
```

### Using Nix

If you are using Nix, the repository ships a `flake.nix` that provides a development shell. To enter it, run:

```bash
nix develop
```

An FHS-compatible shell is also available for toolchains that expect a standard filesystem layout:

```bash
nix develop .#fhs
```

## Tooling

The project uses several tools to ensure code quality and consistency. These tools are configured in the `pyproject.toml` file and in tool-specific files like `ruff.toml` for Ruff.

### Main tools

We use the following tools, most of which are standard in the Python ecosystem:

- **uv**: Package and virtual environment manager
- **ruff**: Linter and code formatter
- **pyrefly**: Static type checker
- **mypy**: Static type checker
- **deptry**: Dependency checker
- **pre-commit**: Git hooks
- **pytest**: Testing framework
- **make**: Task runner
- **zensical**: Documentation site generator (the Material-for-MkDocs successor)

### Running Tools

`make` is the primary task runner. Typing `make help` will show you the available commands.

A `tasks.py` file with [Invoke](https://www.pyinvoke.org/) tasks also exists for a few monorepo-wide operations; Invoke is not part of the default dependency set, so install it separately if you want to run `inv -l`.
