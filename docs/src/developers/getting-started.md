# Getting Started

Start by reading the [core values of Hop3](core-values.md). They shape what counts as a contribution.

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

If you are using Nix, the repository ships a `flake.nix` defining a development shell. To enter it, run:

```bash
nix develop
```

An FHS-compatible shell is also available for toolchains that expect a standard filesystem layout:

```bash
nix develop .#fhs
```

## Tooling

The project lints, formats and type-checks with tools configured in `pyproject.toml` and in tool-specific files like `ruff.toml` for Ruff.

### Main tools

Hop3 uses these tools, most of them standard in the Python ecosystem:

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

`make` is the primary task runner; `make help` shows the available commands.

A `tasks.py` file with [Invoke](https://www.pyinvoke.org/) tasks covers a few monorepo-wide operations. Invoke is not part of the default dependency set, so install it separately if you want to run `inv -l`.
