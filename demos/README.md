# Hop3 Demos

Demo applications and scripts for showcasing Hop3 features.

## Quick Start

```bash
# Run all demos on a server
python -m demos.demo --host <server_ip>

# Run a specific demo
python -m demos.demo --host <server_ip> demo01

# Run multiple demos
python -m demos.demo --host <server_ip> demo01 demo02

# Run your own app
python -m demos.demo --host <server_ip> ~/my-flask-app
```

Note: Run from the hop3 repository root directory.

## Available Demos

### Basic Deployment (demo01-demo09)

Demonstrates different builders and languages.

| Demo | Description | Builder |
|------|-------------|---------|
| demo01 | uWSGI Deployment (Python/Flask) | uwsgi |
| demo02 | Docker Deployment | docker |
| demo03 | Static Site (Nginx) | static |
| demo04 | Node.js Express | nodejs |
| demo05 | Go with Gin | go |
| demo06 | Ruby Sinatra | ruby |
| demo07 | Flask + Gunicorn | python |
| demo08 | Python Poetry | python |
| demo09 | Minimal Go (stdlib only) | go |

### Addons & Features (demo10-demo14)

Demonstrates PostgreSQL, Redis, background workers, and hooks.

| Demo | Description | Addons |
|------|-------------|--------|
| demo10 | PostgreSQL Addon | PostgreSQL |
| demo11 | Background Workers | - |
| demo12 | Backup and Restore | PostgreSQL |
| demo13 | Build Hooks | - |
| demo14 | Redis Addon | Redis |

### Docker with Addons (demo15-demo19)

Demonstrates Docker deployments with database addons.

| Demo | Description | Addons |
|------|-------------|--------|
| demo15 | Docker + PostgreSQL | PostgreSQL |
| demo16 | Docker + Redis | Redis |
| demo17 | Docker Multi-Container | - |
| demo18 | Docker Node.js | - |
| demo19 | Docker Go | - |

### Real-World Applications (demo20-demo26)

Production-ready applications demonstrating Hop3's capabilities.

| Demo | Application | Description | Addons |
|------|-------------|-------------|--------|
| demo20 | Umami | Privacy-focused web analytics | PostgreSQL |
| demo21 | HedgeDoc | Collaborative markdown editor | PostgreSQL |
| demo22 | Radicale | CalDAV/CardDAV server | - |
| demo23 | DokuWiki | Simple wiki (file-based) | - |
| demo24 | Listmonk | Newsletter & mailing list manager | PostgreSQL |
| demo25 | OpenCloud | File sharing platform | - |
| demo26 | Miniflux | RSS/Atom feed reader | PostgreSQL |

### Default Credentials

Applications with web interfaces use these default credentials:

| Demo | Application | Username | Password |
|------|-------------|----------|----------|
| demo20 | Umami | admin | umami |
| demo21 | HedgeDoc | - | (anonymous access) |
| demo22 | Radicale | demo | demo |
| demo23 | DokuWiki | - | (no auth for demo) |
| demo24 | Listmonk | admin | admin123 |
| demo25 | OpenCloud | admin | changeme |
| demo26 | Miniflux | admin | admin123 |

Use `python -m demos.demo --list` to see all available demos.

## Command Reference

```
usage: demo.py --host HOST [options] [demos...]

Required:
  -H, --host HOST          Target server IP address

Server Options:
  --ssh-user USER          SSH user for server connection (default: root)
  --skip-install           Skip Hop3 installation (assume already installed)
  -l, --local              Sync local hop3-server code via rsync
  --demo-dir DIR           Additional directory to search for demos (repeatable)

Authentication:
  --admin-user USER        Admin username to create (default: admin)
  --admin-email EMAIL      Admin email address (default: admin@example.com)
  --admin-password PWD     Admin password (auto-generated if not specified)

Demo Execution:
  -k, --keep               Keep deployed apps running after demo completes
  -p, --pause SECS         Pause between demo steps in seconds (default: 0.5)

Output Control:
  -v, --verbose            Show detailed output and stack traces
  -q, --quiet              Minimal output (phases and results only)
  -s, --silent             No output except errors (errors go to stderr)

Information:
  -h, --help               Show this help message and exit
  --list                   List available demos
  --inventory              Show detailed inventory of all demos
```

## Common Use Cases

### Development Mode

Test local code changes without committing:

```bash
# Sync local code to server and run demo
python -m demos.demo --host <server_ip> --local demo01

# Keep apps running for debugging
python -m demos.demo --host <server_ip> --local --keep demo02
```

The `--local` flag uses rsync to sync your local hop3-server code to the server.

### Recording Screencasts

```bash
# Longer pauses, keep apps visible
python -m demos.demo --host <server_ip> --pause 2 --keep
```

### CI/CD Integration

```bash
# Minimal output for CI logs
python -m demos.demo --quiet --host <server_ip> demo01

# Silent mode (errors to stderr only)
python -m demos.demo --silent --host <server_ip> demo01

# Exit code: 0 = all passed, 1 = some failed
```

### Demo Inventory

```bash
# View detailed info about all demos
python -m demos.demo --inventory

# Include external demo directories
python -m demos.demo --inventory --demo-dir ~/my-demos
```

### External Applications

Run any Hop3-compatible application:

```bash
# Your app with hop3.toml, Dockerfile, or requirements.txt
python -m demos.demo --host <server_ip> ~/my-project

# Keep it running after demo
python -m demos.demo --host <server_ip> ~/my-project --keep
```

## Prerequisites

- **Target Server**: Ubuntu 22.04 or 24.04 with SSH root access
- **Local Machine**:
  - Python 3.10+
  - Hop3 CLI installed (`pip install hop3-cli`)
  - SSH key authentication configured

## Troubleshooting

### SSH Connection Issues

```bash
# Test connection
ssh root@<server_ip> echo "Connected"

# Set up SSH keys if needed
ssh-copy-id root@<server_ip>
```

### hop3 CLI Not Found

```bash
pip install hop3-cli
```

### Installation Takes Too Long

Initial installation takes 5-10 minutes. Use `--skip-install` if Hop3 is already installed.

## Directory Structure

```
demos/
├── __init__.py         # Package marker
├── demo.py             # Entry point
├── lib/                # Shared utilities
│   ├── __init__.py     # Exports
│   ├── app.py          # Common app management routines
│   ├── cli.py          # Argument parsing
│   ├── commands.py     # run_local, run_ssh, run_hop3
│   ├── context.py      # DemoContext, DemoResult, OutputLevel
│   ├── discovery.py    # Demo discovery and resolution
│   ├── display.py      # Banner, list, inventory display
│   ├── generic_demo.py # Generic demo for any Hop3 app
│   ├── output.py       # Terminal output helpers
│   ├── phases.py       # Execution phases (prerequisites, CLI, run)
│   └── server.py       # Server setup, sync, update
├── demo01/             # uWSGI (Flask)
├── demo02/             # Docker
├── ...
└── demo26/             # Miniflux (RSS reader)
```

## Creating a New Demo

### Option 1: Custom Demo Script

1. Create directory: `demos/demoXX/`
2. Create `demo-script.py` with `TITLE`, `DESCRIPTION`, and `run(ctx)` function
3. Add sample application files in `app/` subdirectory
4. The demo is auto-discovered

### Option 2: Generic Demo (No Script Needed)

Just point to any Hop3-compatible application:

```bash
python -m demos.demo --host <server_ip> ~/my-app
```

The generic demo will automatically:
- Detect app type (Python, Docker, Node.js, etc.)
- Deploy using the appropriate builder
- Set up hostname and proxy
- Test the deployment
- Clean up (unless `--keep`)
