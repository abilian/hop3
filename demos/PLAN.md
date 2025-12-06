# Hop3 Demo System

## Overview

A unified demo system for showcasing Hop3 features. Supports multiple demos that can be run individually or in sequence, with development mode for testing local code changes.

## Target Audience

- Developers evaluating Hop3
- Users following along with documentation
- Marketing/documentation team creating screencasts
- Hop3 developers testing changes

## Architecture

```
demos/
├── demo.py             # Demo launcher (entry point)
├── lib/                # Shared utilities
│   ├── __init__.py
│   ├── app.py          # Common app management routines
│   ├── commands.py     # run_local, run_ssh, run_hop3
│   ├── context.py      # DemoContext dataclass
│   ├── generic_demo.py # Generic demo for any Hop3 app
│   ├── output.py       # Terminal output helpers
│   └── server.py       # Server setup, sync, update
├── demo1/
│   ├── demo-script.py  # Demo metadata + run() function
│   └── hello-hop3/     # Sample Flask app
└── demo2/
    ├── demo-script.py  # Demo metadata + run() function
    └── hello-docker/   # Sample Docker app
```

## Command-Line Interface

### Synopsis

```
python demos/demo.py --host HOST [options] [demos...]
python demos/demo.py --help
python demos/demo.py --list
```

### Help Output

```
usage: demo.py --host HOST [options] [demos...]

Hop3 Demo Runner - Interactive demonstrations of Hop3 deployment features.

This tool runs demos that showcase Hop3 capabilities. Each demo deploys a
sample application, tests it, and demonstrates lifecycle management.

Required:
  -H, --host HOST          Target server IP address

Server Options:
  --ssh-user USER          SSH user for server connection (default: root)
  --skip-install           Skip Hop3 installation (assume already installed)
  -l, --local              Sync local hop3-server code via rsync

Authentication:
  --admin-user USER        Admin username to create (default: admin)
  --admin-email EMAIL      Admin email address (default: admin@example.com)
  --admin-password PWD     Admin password (auto-generated if not specified)

Demo Execution:
  -k, --keep               Keep deployed apps running after demo completes
  -p, --pause SECS         Pause between demo steps in seconds (default: 0.5)
  -v, --verbose            Show detailed output and stack traces

Information:
  -h, --help               Show this help message and exit
  --list                   List available built-in demos and exit

Demos:
  Specify one or more demos to run. If none specified, runs all built-in demos.

  Built-in demos (in demos/ directory):
    demo1                  uWSGI deployment (Python/Flask)
    demo2                  Docker deployment

  You can also specify:
    - External paths: ~/my-project or /path/to/demo
      (runs demo-script.py if present, otherwise runs generic demo)
    - 'all': Explicitly run all built-in demos

Examples:
  # Run all demos on a server
  python demos/demo.py --host 46.62.169.221

  # Run a specific demo
  python demos/demo.py --host 46.62.169.221 demo1

  # Run multiple demos
  python demos/demo.py --host 46.62.169.221 demo1 demo2

  # Development: test local code changes
  python demos/demo.py --host 46.62.169.221 --local demo1

  # Keep apps running for debugging
  python demos/demo.py --host 46.62.169.221 --keep demo2

  # Run external demo from any directory
  python demos/demo.py --host 46.62.169.221 ~/my-project

  # Recording screencast with longer pauses
  python demos/demo.py --host 46.62.169.221 --pause 2 --keep

  # Mix built-in and external demos
  python demos/demo.py --host 46.62.169.221 demo1 ~/my-app --keep
```

### Option Reference

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--host HOST` | `-H` | (required) | Target server IP address |
| `--ssh-user USER` | | `root` | SSH user for server connection |
| `--skip-install` | | false | Skip Hop3 installation phase |
| `--local` | `-l` | false | Use local code via rsync |
| `--admin-user USER` | | `admin` | Admin username to create |
| `--admin-email EMAIL` | | `admin@example.com` | Admin email address |
| `--admin-password PWD` | | (random) | Admin password |
| `--keep` | `-k` | false | Don't destroy apps after demo |
| `--pause SECS` | `-p` | `0.5` | Pause between steps |
| `--verbose` | `-v` | false | Verbose output |
| `--help` | `-h` | | Show help and exit |
| `--list` | | | List available demos and exit |

### Demo Arguments

Demo arguments are positional and come after all options:

1. **Built-in demo names**: `demo1`, `demo2`, etc.
   - Auto-discovered from `demos/` subdirectories containing `demo-script.py`

2. **External paths**: `~/my-project`, `/path/to/demo`
   - If `demo-script.py` exists: runs custom demo script
   - If no `demo-script.py`: runs **generic demo** (deploy, test, cleanup)
   - Supports `~` expansion and relative paths

3. **Keyword `all`**: Run all built-in demos
   - Case-insensitive (`all`, `ALL`, `All`)

4. **Default**: If no demos specified, equivalent to `all`

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All demos completed successfully |
| 1 | One or more demos failed |
| 2 | Invalid arguments or missing required options |
| 130 | Interrupted by user (Ctrl+C) |

## Demo Flow

### Phase 1: Prerequisites

1. Verify SSH access to server
2. Check Ubuntu version (22.04 or 24.04)
3. Check if Hop3 is installed
4. Install or update Hop3 (supports `--local` for dev mode)

### Phase 2: CLI Configuration

1. Check hop3 CLI availability
2. Create admin user via SSH (or login if exists)
3. Verify authentication

### Phase 3: Run Selected Demos

Each demo has its own `demo-script.py` with a `run(ctx)` function that:
- Deploys a sample application
- Sets up hostname/proxy
- Tests the deployment
- Demonstrates app management
- Cleans up (unless `--keep`)

## Key Features

### Development Mode (`--local`)

Syncs local hop3-server code to server via rsync:
```bash
python demos/demo.py --host 46.62.169.221 --local demo1
```

This allows testing changes without committing/pushing.

### Multi-Demo Support

Run demos individually or in sequence:
```bash
python demos/demo.py --host 46.62.169.221 demo1           # Single demo
python demos/demo.py --host 46.62.169.221 demo1 demo2     # Multiple
python demos/demo.py --host 46.62.169.221                 # All demos
```

### External Demos

Run demos from any directory:
```bash
python demos/demo.py --host 46.62.169.221 ~/my-project
python demos/demo.py --host 46.62.169.221 /tmp/test-demo
```

If the directory contains a `demo-script.py`, it runs the custom script.
Otherwise, the **generic demo** runs automatically.

### Generic Demo

When pointing to a directory without `demo-script.py`, the launcher runs a
generic demo that works with any Hop3 application:

1. **Detects app type** by looking for:
   - `hop3.toml` - Hop3 configuration
   - `Dockerfile` - Docker-based app
   - `requirements.txt` - Python app
   - `package.json` - Node.js app
   - `Procfile` - Heroku-style app

2. **Derives app name** from the directory name (sanitized)

3. **Runs standard workflow**:
   - Deploy the application
   - Set hostname (`<app-name>.hop.demo`)
   - Redeploy to apply hostname
   - Check status
   - Test via curl (if web app)
   - Cleanup (unless `--keep`)

Example:
```bash
# Deploy any Hop3-compatible app
python demos/demo.py --host 46.62.169.221 ~/my-flask-app

# Keep it running for testing
python demos/demo.py --host 46.62.169.221 ~/my-flask-app --keep
```

### Auto-Discovery

Built-in demos are automatically discovered from subdirectories of `demos/` that contain a `demo-script.py` file.

## Creating a New Demo

### Built-in Demo

1. Create directory: `demos/demo3/`

2. Create `demo-script.py`:
```python
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

TITLE = "Demo 3: My Feature"
DESCRIPTION = "What this demo showcases"

APP_NAME = "my-app"
APP_DIR = Path(__file__).parent / "my-app"
DEFAULT_HOSTNAME = "a3.hop.demo"

def run(ctx: DemoContext) -> None:
    from lib import (
        deploy_app,
        set_hostname,
        redeploy_app,
        check_app_status,
        test_app_via_curl,
        cleanup_app,
        print_header,
    )

    app_url = f"https://{DEFAULT_HOSTNAME}"

    print_header("Deploying Application")
    deploy_app(ctx, APP_NAME, APP_DIR)
    set_hostname(ctx, APP_NAME, DEFAULT_HOSTNAME)
    redeploy_app(ctx, APP_NAME, APP_DIR)
    check_app_status(ctx, APP_NAME)
    test_app_via_curl(ctx, app_url, expected_content="Expected response")
    cleanup_app(ctx, APP_NAME, app_url)
```

3. Add sample application files in `demos/demo3/my-app/`

4. Test: `python demos/demo.py --host <server_ip> demo3`

### External Demo (Custom Script)

Same structure as built-in, but can live anywhere:
```
~/my-project/
├── demo-script.py    # Custom demo logic
└── my-app/           # Your application
    ├── app.py
    ├── requirements.txt
    └── hop3.toml
```

Run with: `python demos/demo.py --host <server_ip> ~/my-project`

### External Demo (Generic / No Script)

Just point to any Hop3-compatible application directory:
```
~/my-flask-app/
├── app.py
├── requirements.txt
└── hop3.toml
```

Run with: `python demos/demo.py --host <server_ip> ~/my-flask-app`

The generic demo will:
- Use `my-flask-app` as the app name
- Deploy, configure hostname, test, and cleanup automatically

## Output Style

```
╔════════════════════════════════════════════════════════════════════╗
║  Phase 1: Prerequisites                                            ║
╚════════════════════════════════════════════════════════════════════╝

→ Verifying SSH access to the server...
✓ Connected to 46.62.169.221

→ Checking Ubuntu version...
✓ Ubuntu 24.04 LTS detected
```

## Available Built-in Demos

| Demo | Description | App Hostname |
|------|-------------|--------------|
| demo1 | uWSGI deployment (Python/Flask) | a1.hop.demo |
| demo2 | Docker deployment | a2.hop.demo |

## Quick Reference

```bash
# Basic usage
python demos/demo.py --host 46.62.169.221

# Development workflow
python demos/demo.py --host 46.62.169.221 --local demo1

# Debugging (keep apps running)
python demos/demo.py --host 46.62.169.221 --keep demo2

# Screencast recording
python demos/demo.py --host 46.62.169.221 --pause 2 --keep

# External project
python demos/demo.py --host 46.62.169.221 ~/my-project --keep

# List available demos
python demos/demo.py --list

# Help
python demos/demo.py --help
```
