# hop3-server

Core server for the Hop3 Platform-as-a-Service.

## Overview

hop3-server is the central orchestrator that handles application deployments, process management, reverse proxy configuration, and addon services. It provides a JSON-RPC API for communication with hop3-cli and hop3-tui.

## Features

- **Git-push deployments**: Deploy applications via `git push`
- **Automatic build system**: Detects language (Python, Node, Ruby, Go, Rust, etc.) and builds automatically
- **Process management**: Manages app processes based on Procfile via uWSGI
- **Reverse proxy**: Nginx/Caddy/Traefik with automatic SSL certificates
- **Addon services**: PostgreSQL, MySQL, Redis management
- **Plugin architecture**: Extensible via pluggy-based plugins
- **JSON-RPC API**: For CLI and TUI communication

## Installation

### Production

```bash
curl -LsSf https://hop3.cloud/install-server.py | sudo python3 -
```

### Development

```bash
pip install hop3-server
```

## Quick Start

```bash
# Run the server
hop3-server serve

# Run with specific host/port
hop3-server serve --host 0.0.0.0 --port 8000
```

## Configuration

Server configuration via environment variables or `/etc/hop3/config.toml`:

| Variable | Description | Default |
|----------|-------------|---------|
| `HOP3_HOME` | Home directory | `/home/hop3` |
| `HOP3_DATABASE_URL` | Database URL | `sqlite:///hop3.db` |
| `HOP3_SECRET_KEY` | JWT signing key | (required) |

## Architecture

```
hop3-server/
├── src/hop3/
│   ├── server/           # Litestar ASGI application
│   │   ├── asgi.py       # App factory
│   │   └── controllers/  # API endpoints
│   ├── commands/         # RPC command handlers
│   ├── deployers/        # Deployment orchestration
│   ├── orm/              # SQLAlchemy models
│   ├── plugins/          # Plugin system
│   │   ├── build/        # Builders, language toolchains
│   │   ├── deploy/       # Deployers (uWSGI, static)
│   │   ├── proxy/        # Nginx, Caddy, Traefik
│   │   └── addons/       # PostgreSQL, MySQL, Redis
│   ├── core/             # Core abstractions
│   │   ├── protocols.py  # Plugin protocols
│   │   └── hookspecs.py  # Hook specifications
│   └── toolchains/       # Language toolchains
└── tests/
    ├── a_unit/           # Unit tests
    ├── b_integration/    # Integration tests
    └── c_e2e/            # End-to-end tests (Docker, real deploy)
```

### Filesystem Layout

```
/home/hop3/
├── apps/<app_name>/
│   ├── git/              # Bare git repository
│   ├── src/              # Checked-out source code
│   ├── data/             # Persistent data
│   └── log/              # Log files
├── nginx/                # Nginx configs and certs
├── uwsgi-available/      # uWSGI configs
├── uwsgi-enabled/        # Active uWSGI configs
└── hop3.db               # SQLite database
```

## Development

```bash
# Unit tests
uv run pytest tests/a_unit/ -v

# Integration tests
uv run pytest tests/b_integration/ -v

# End-to-end tests (requires Docker)
uv run pytest tests/c_e2e/ -v

# Lint and format
uv run ruff check src/
uv run ruff format src/
```

## Documentation

- [User Guide](../../docs/src/guide.md)
- [Plugin Development](../../docs/src/dev/plugin-development.md)

## Related Packages

- [hop3-cli](../hop3-cli/) - CLI client for this server
- [hop3-tui](../hop3-tui/) - TUI client for this server
- [hop3-installer](../hop3-installer/) - Installation tools

## License

Apache-2.0 - Copyright (c) 2024-2026, Abilian SAS
