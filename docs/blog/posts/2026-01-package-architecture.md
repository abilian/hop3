---
date: 2026-03-03
template: blog_post.html
description: How we split Hop3 into 5 focused packages for better maintainability.
tags:
  - Architecture
  - Engineering
---

# From Monolith to Modular: Hop3's Package Architecture

When we started Hop3, everything lived in a single package. As the codebase grew, this became a problem. The CLI imported server code. Tests pulled in production dependencies. A change to the installer could break the TUI. We needed to split things up.

## The Problem with Monoliths

Our original structure looked like this:

```
hop3/
├── cli/           # Command-line interface
├── server/        # Core server code
├── installer/     # Installation scripts
├── tui/           # Terminal UI
├── testing/       # Test utilities
└── ...
```

Everything was importable from everywhere. This caused several issues:

1. **Dependency bloat**: Installing the CLI pulled in server dependencies
2. **Circular imports**: CLI needed server types, server needed CLI utilities
3. **Test pollution**: Test fixtures leaked into production code
4. **Versioning confusion**: One version number for unrelated components

## The Solution: Five Packages

We split Hop3 into five focused packages, each with a clear responsibility:

```
packages/
├── hop3-server/    # Core platform (runs on server)
├── hop3-cli/       # Client CLI (runs on developer machine)
├── hop3-installer/ # Installation toolkit
├── hop3-tui/       # Terminal UI (optional)
└── hop3-testing/   # Test framework (dev only)
```

### hop3-server

The core platform that runs on your deployment server.

**Entry point**: `hop3-server serve`

**Responsibilities**:
- JSON-RPC API for CLI/TUI communication
- Application deployment orchestration
- Reverse proxy configuration
- Database addon management
- Process management via uWSGI

**Dependencies**: Litestar, SQLAlchemy, Pluggy, Dishka

**Who uses it**: Server administrators

### hop3-cli

A thin client for developers to interact with Hop3 servers.

**Entry point**: `hop3` or `hop`

**Responsibilities**:
- Parse and validate commands
- Manage SSH tunnels to remote servers
- Send RPC calls and display responses
- Handle authentication

**Dependencies**: Rich, jsonrpcclient, requests, sshtunnel

**Who uses it**: Developers deploying apps

### hop3-installer

Tools for installing Hop3, with minimal dependencies.

**Entry points**:
- `hop3-install` - Production installer for end users
- `hop3-deploy` - Developer deployment tool

**Key feature**: Uses only Python stdlib for the installer scripts themselves. This means you can `curl | python` without pre-installing anything.

**Who uses it**: Server administrators, Hop3 developers

### hop3-tui

A terminal UI built with Textual for keyboard-driven server management.

**Entry point**: `hop3-tui`

**Responsibilities**:
- Dashboard with system metrics
- Application management
- Real-time log viewing
- Environment variable editing

**Dependencies**: Textual

**Who uses it**: Administrators who prefer TUI over CLI

### hop3-testing

Testing utilities and fixtures for E2E testing.

**Entry point**: `hop3-test`

**Responsibilities**:
- Pytest fixtures for integration/E2E testing
- Docker and SSH target management
- Test catalog and discovery
- Diagnostic collection on failures

**Who uses it**: Hop3 developers, CI systems

## Communication Between Packages

The packages communicate through well-defined interfaces:

```
┌─────────────┐         ┌─────────────────┐
│  hop3-cli   │──JSON───│   hop3-server   │
│  hop3-tui   │  -RPC   │                 │
└─────────────┘         └─────────────────┘
        │                       │
        │                       │
┌───────▼───────┐       ┌───────▼───────┐
│ hop3-installer│       │ hop3-testing  │
│ (deploys both)│       │ (tests both)  │
└───────────────┘       └───────────────┘
```

- **CLI/TUI → Server**: JSON-RPC over SSH tunnel or HTTPS
- **Installer → Both**: Installs packages via pip/uv
- **Testing → Both**: Deploys and validates via fixtures

## Benefits

### 1. Clear Dependencies

Each package declares only what it needs:

```toml
# hop3-cli/pyproject.toml
dependencies = [
    "jsonrpcclient>=4.0",
    "requests>=2.32",
    "rich>=13.0",
    "sshtunnel>=0.4",
]
# No SQLAlchemy, no Litestar, no test utilities
```

### 2. Independent Versioning

We can release a CLI bugfix without touching the server:

```
hop3-server 0.4.0
hop3-cli 0.4.1  # Bugfix release
```

### 3. Easier Testing

Test dependencies stay in hop3-testing:

```toml
# hop3-testing/pyproject.toml
dependencies = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "docker>=7.0",
]
```

Production packages don't carry test baggage.

### 4. Simpler CI

We can test packages in parallel:

```yaml
jobs:
  test-server:
    run: pytest packages/hop3-server
  test-cli:
    run: pytest packages/hop3-cli
  test-integration:
    needs: [test-server, test-cli]
    run: pytest packages/hop3-testing
```

### 5. Optional Components

Don't need the TUI? Don't install it:

```bash
pip install hop3-cli  # Just the CLI
pip install hop3-tui  # Add TUI if wanted
```

## Lessons Learned

### When to Split

Split when you have:
- Different deployment targets (server vs. local machine)
- Different user personas (admin vs. developer)
- Optional functionality (TUI, testing tools)
- Dependency conflicts

### When to Keep Together

Keep together when:
- Components always change together
- Splitting would create circular dependencies
- The split boundary is unclear

### Shared Code

For code shared between packages, we had two options:

1. **Duplicate it** (small utilities)
2. **Create a shared package** (we didn't need this yet)

We chose duplication for now. If patterns emerge, we'll extract a `hop3-common` package.

## The Workspace

We use a uv workspace to manage all packages:

```toml
# pyproject.toml (root)
[tool.uv.workspace]
members = ["packages/*"]
```

This lets us:
- Install all packages in development: `uv sync`
- Run tests across packages: `pytest packages/`
- Build all packages: `uv build --all`

## Try It Yourself

Browse the package structure:

```bash
git clone https://github.com/abilian/hop3
ls packages/
```

Each package has its own README explaining its purpose.

---

*Related: [Hop3's Plugin Architecture](2026-01-plugin-architecture.md) explains how we use Pluggy for extensibility. For more documentation, see the [Architecture Guide](/developers/architecture/).*
