# hop3-server

Core server for the Hop3 Platform-as-a-Service.

## Overview

hop3-server is the central orchestrator that handles application deployments, process management, reverse proxy configuration, and addon services. It provides a JSON-RPC API for communication with hop3-cli and hop3-tui.

## Features

- **Git-push deployments** - Deploy applications via `git push`
- **Automatic build system** - Detects language (Python, Node, Ruby, Go, Rust, etc.) and builds automatically
- **Process management** - Manages app processes based on Procfile via uWSGI
- **Reverse proxy** - Nginx/Caddy/Traefik with automatic SSL certificates
- **Addon services** - PostgreSQL, MySQL, Redis management
- **Plugin architecture** - Extensible via pluggy-based plugins
- **JSON-RPC API** - For CLI and TUI communication

## Installation

### For development

```bash
# From workspace root
cd packages/hop3-server
uv pip install -e ".[dev]"
```

### Production installation

Use hop3-installer:
```bash
curl -LsSf https://hop3.cloud/install-server.py | sudo python3 -
```

## Quick Start

```bash
# Run the server
hop3-server serve

# Run with specific host/port
hop3-server serve --host 0.0.0.0 --port 8000
```

## Architecture

```
hop3-server/
├── src/hop3/
│   ├── server/              # Litestar ASGI application
│   │   ├── asgi.py          # App factory
│   │   ├── controllers/     # API endpoints
│   │   └── security/        # Authentication
│   ├── commands/            # RPC command handlers
│   ├── deployers/           # Deployment orchestration
│   ├── orm/                 # SQLAlchemy models (App, EnvVar)
│   ├── plugins/             # Plugin system
│   │   ├── build/           # Builders, language toolchains
│   │   ├── deploy/          # Deployers (uWSGI, static)
│   │   ├── proxy/           # Nginx, Caddy, Traefik
│   │   ├── oses/            # OS implementations
│   │   ├── postgresql/      # PostgreSQL addon
│   │   ├── mysql/           # MySQL addon
│   │   └── redis/           # Redis addon
│   ├── core/                # Core abstractions
│   │   ├── protocols.py     # Plugin protocols
│   │   ├── hookspecs.py     # Hook specifications
│   │   └── plugins.py       # Plugin manager
│   ├── toolchains/          # Language toolchains
│   ├── run/                 # Runtime process management
│   └── project/             # Procfile parsing
└── tests/
    ├── a_unit/              # Unit tests
    ├── b_integration/       # Integration tests
    ├── c_system/            # System tests
    └── d_e2e/               # End-to-end tests
```

### Deployment Flow

```
git push → Git hook → Deployer → Builder → Language Toolchain → uWSGI config → Nginx config
```

### Filesystem Layout

```
/home/hop3/
├── apps/<app_name>/
│   ├── git/           # Bare git repository
│   ├── src/           # Checked-out source code
│   ├── data/          # Persistent data
│   ├── log/           # Log files
│   └── venv/          # Python virtualenv (if applicable)
├── nginx/             # Nginx configs and certs
├── uwsgi-available/   # uWSGI configs
├── uwsgi-enabled/     # Active uWSGI configs (symlinks)
└── hop3.db            # SQLite database
```

## Configuration

Server configuration via environment variables or `/etc/hop3/config.toml`:

| Variable | Description | Default |
|----------|-------------|---------|
| `HOP3_HOME` | Home directory | `/home/hop3` |
| `HOP3_DATABASE_URL` | Database URL | `sqlite:///hop3.db` |
| `HOP3_SECRET_KEY` | JWT signing key | (required) |

## Development

### Running tests

```bash
# Unit tests
uv run pytest tests/a_unit/ -v

# Integration tests
uv run pytest -n 4 tests/b_integration/ -v

# System tests (requires Docker)
uv run pytest tests/c_system/ -v

# E2E tests (slow)
uv run pytest tests/d_e2e/ -v
```

### Code quality

```bash
uv run ruff check src/
uv run ruff format src/
uv run pyright src/
```

## Plugin Development

See [Plugin Development Guide](../../docs/src/dev/plugin-development.md) for creating:
- Language toolchains (new language support)
- Addons (new backing services)
- Deployers (new runtime strategies)
- Proxies (new reverse proxy support)

## Documentation

- **User Guide**: [Main documentation](../../docs/src/guide.md)
- **System Architecture**: [Architecture overview](../../docs/src/dev/architecture.md)
- **Plugin Development**: [Plugin guide](../../docs/src/dev/plugin-development.md)
- **Testing Strategy**: [Testing guide](../../docs/src/dev/testing-strategy.md)
- **Package Internals**: [Deep-dive documentation](./docs/internals.md)

## Related Packages

- [hop3-cli](../hop3-cli/) - CLI client for this server
- [hop3-tui](../hop3-tui/) - TUI client for this server
- [hop3-installer](../hop3-installer/) - Installation tools

## License

Apache-2.0 - Copyright (c) 2024-2025, Abilian SAS
