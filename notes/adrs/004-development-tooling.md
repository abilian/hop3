# ADR 004: Development Tooling

**Status**: Active
**Type**: Process
**Created**: 2025-10-08

## Summary

This ADR documents the selection and rationale for the core development tools used in the Hop3 project. These tools form the foundation of our development workflow, covering package management, task automation, code quality, testing, and deployment.

## Context and Goals

A modern Python project requires a comprehensive toolchain to ensure developer productivity, code quality, and maintainability. The goals for our tooling decisions are:

1. **Developer Experience**: Tools should be fast, intuitive, and minimize friction
2. **Modern Best Practices**: Adopt contemporary tools that align with Python ecosystem trends
3. **Consistency**: Use tools that enforce consistent coding standards across the team
4. **Performance**: Prefer faster tools over legacy alternatives where quality is equivalent
5. **Simplicity**: Minimize the number of tools and configuration complexity
6. **Compliance**: Ensure tools support licensing and security compliance requirements

## Decision

### Package and Dependency Management: uv

**Tool**: [uv](https://github.com/astral-sh/uv) (by Astral)

**Rationale**:
- **Speed**: Significantly faster than pip/poetry (10-100x faster)
- **Workspace Support**: Native monorepo/workspace support for our multi-package architecture
- **Lock Files**: Deterministic dependency resolution with `uv.lock`
- **Modern**: Active development, designed for contemporary Python workflows
- **pip-compatible**: Drop-in replacement for pip with familiar interface

**Replaced**: pip, pip-tools, poetry, pipenv

**Configuration**: `pyproject.toml` with `[tool.uv]` and `[tool.uv.workspace]` sections

### Task Runner: Make

**Tool**: [Make](https://www.gnu.org/software/make/) + [Invoke](https://www.pyinvoke.org/)

**Design**:
- The `Makefile` in the repository root is the primary task runner.
- `tasks.py` provides Invoke-based tasks for sub-repository management.
- Both serve CI/CD and developer workflows.

### Linting and Formatting: Ruff

**Tool**: [Ruff](https://github.com/astral-sh/ruff)

**Rationale**:
- **Speed**: 10-100x faster than pylint/flake8
- **Comprehensive**: Combines multiple tools (flake8, isort, pyupgrade, etc.) into one
- **Compatible**: Implements most rules from popular linters
- **Formatter**: Includes Black-compatible code formatter
- **Easy**: Single tool configuration, minimal setup

**Replaced**: flake8, black, isort, pyupgrade, pylint

**Configuration**: `pyproject.toml` with `[tool.ruff]` section

### Testing Framework: pytest

**Tool**: [pytest](https://pytest.org/)

**Rationale**:
- **De facto standard**: Most widely used Python testing framework
- **Rich ecosystem**: Extensive plugin ecosystem (pytest-cov, pytest-asyncio, etc.)
- **Fixtures**: Powerful dependency injection for test setup
- **Parametrization**: Easy data-driven testing
- **Readable**: Clear, pythonic test syntax

**Plugins Used**:
- pytest-asyncio: Async test support
- pytest-cov: Coverage reporting
- pytest-beartype: Runtime type checking
- pytest-random-order: Test randomization

**Configuration**: `pyproject.toml` with `[tool.pytest.ini_options]` section

### Pre-commit Hooks: pre-commit

**Tool**: [pre-commit](https://pre-commit.com/)

**Rationale**:
- **Industry Standard**: Widely adopted for git hook management
- **Multi-language**: Supports hooks for various languages
- **Automatic Updates**: Can auto-update hook versions
- **Consistent**: Ensures all developers run the same checks

**Configuration**: `.pre-commit-config.yaml`

### Type Checking: Pyrefly

**Tool**: [Pyrefly](https://github.com/tmke8/pyrefly) with [ty](https://github.com/tmke8/ty) (experimental)

**Rationale**:
- **Modern Approach**: New generation type checker addressing limitations of traditional tools
- **Fast**: Performance-focused implementation
- **Accurate**: Improved type inference and error detection
- **Future**: Represents the evolution of Python type checking

**Experimental Tool - ty**:
- **Advanced Types**: Experimental type system extensions
- **Research**: Exploring next-generation type checking capabilities
- **Evaluation**: Testing for potential adoption in the future

**Legacy Support**: Mypy/Pyright configurations maintained for compatibility but Pyrefly is the primary tool

**Configuration**: `pyproject.toml` (tool-specific sections as needed)

### Deployment Automation: pyinfra

**Tool**: [pyinfra](https://pyinfra.com/)

**Rationale**:
- **Python-native**: Infrastructure as code in Python
- **Agentless**: SSH-based, no agents to install
- **Fast**: Parallel execution across hosts
- **Simple**: Easier than Ansible for Python developers

**Configuration**: `installer/install-hop.py`

### Containerization: Docker

**Tool**: [Docker](https://www.docker.com/)

**Rationale**:
- **E2E Testing**: Provides isolated environments for end-to-end tests
- **Reproducibility**: Consistent testing environments across machines
- **Industry Standard**: De facto standard for containerization

**Usage**: E2E test infrastructure (`packages/hop3-server/tests/d_e2e/docker/`)

### Documentation: MkDocs

**Tool**: [MkDocs](https://www.mkdocs.org/) with Material theme

**Rationale**:
- **Markdown-based**: Easy to write and maintain
- **Beautiful**: Material theme provides modern, professional look
- **Features**: Search, navigation, code highlighting
- **Plugins**: Rich plugin ecosystem (mkdocstrings, git-revision-date, etc.)

**Configuration**: `mkdocs.yml`

**Plugins Used**:
- mkdocs-material: Modern theme
- mkdocstrings: API documentation from docstrings
- mkdocs-git-revision-date: Show last update dates

### Isolated Testing: Nox

**Tool**: [Nox](https://nox.thea.codes/)

**Rationale**:
- **Isolation**: Each test session in its own virtual environment
- **Python-based**: Configuration in Python, not YAML
- **Matrix Testing**: Easy testing across Python versions
- **Audit Tasks**: Used for security audits (pip-audit, safety)

**Configuration**: `noxfile.py`

### License Compliance: REUSE

**Tool**: [REUSE](https://reuse.software/)

**Rationale**:
- **Standard**: FSFE standard for license compliance
- **Simple**: Easy to verify all files have proper license headers
- **Automated**: Can be checked in CI/CD

**Configuration**: `.reuse/` directory and license headers in files

### Additional Tools

- **abilian-devtools**: Internal development utilities
- **import-linter**: Enforce module dependency boundaries
- **deptry**: Detect unused dependencies
- **SBOM Tools**: cyclonedx-bom, spdx-tools for software bill of materials generation

## Consequences

### Benefits

1. **Performance**: Modern, fast tools (uv, Ruff) significantly improve developer experience
2. **Consistency**: Single source of truth for code formatting and linting
3. **Simplicity**: Fewer tools to learn and configure (Ruff replaces 5+ tools)
4. **Modern Stack**: Aligned with current Python ecosystem best practices
5. **Quality**: Comprehensive tooling ensures high code quality
6. **Compliance**: Built-in support for licensing and security requirements

### Drawbacks

1. **Tooling Proliferation**: Still quite a few tools despite consolidation efforts

### Trade-offs

1. **Speed vs Maturity**: Chose faster, newer tools (uv, Ruff) over more mature alternatives (poetry, pylint)
2. **Single Tool vs Best of Breed**: Consolidated where possible (Ruff) but kept separate tools where specialized (pytest, pirefly, mypy)

## References

- [uv Documentation](https://github.com/astral-sh/uv)
- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [pytest Documentation](https://docs.pytest.org/)
- [Pyrefly](https://github.com/tmke8/pyrefly)
- [ty - Experimental Type System](https://github.com/tmke8/ty)
- [pyinfra Documentation](https://docs.pyinfra.com/)
- [REUSE Specification](https://reuse.software/spec/)

## Notes

This tooling stack represents a modern, performance-focused approach to Python development. The emphasis on speed (uv, Ruff) and developer experience aligns with our goal of maintaining high development velocity while ensuring code quality.

The choice of Rust-based tools (uv, Ruff) reflects a broader industry trend toward using systems programming languages for developer tools where performance matters.

We intentionally avoided tool proliferation by:
- Using Ruff instead of 5+ separate linting tools
- Using uv instead of multiple package management tools

However, we kept specialized tools (pytest, Pyrefly, mkdocs) where they excel in their domain rather than trying to force everything into a single tool.

For type checking specifically, we've chosen to adopt Pyrefly as a next-generation type checker, moving away from the traditional Mypy/Pyright approach. This decision reflects our commitment to exploring and adopting emerging tools that may offer better performance and accuracy. We're also experimenting with ty, which pushes the boundaries of Python's type system even further.
