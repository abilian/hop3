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
├── demo.py           # Unified entry point
├── lib/              # Shared utilities
│   ├── __init__.py
│   ├── app.py        # Common app management routines
│   ├── commands.py   # run_local, run_ssh, run_hop3
│   ├── context.py    # DemoContext dataclass
│   ├── output.py     # Terminal output helpers
│   └── server.py     # Server setup, sync, update
├── demo1/
│   ├── demo-script.py  # Demo metadata + run() function
│   └── hello-hop3/     # Sample Flask app
└── demo2/
    ├── demo-script.py  # Demo metadata + run() function
    └── hello-docker/   # Sample Docker app
```

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
- Cleans up (unless `--no-cleanup`)

## Key Features

### Development Mode (`--local`)

Syncs local hop3-server code to server via rsync:
```bash
python demos/demo.py 46.62.169.221 demo1 --local
```

This allows testing changes without committing/pushing.

### Multi-Demo Support

Run demos individually or in sequence:
```bash
python demos/demo.py 46.62.169.221 demo1        # Single demo
python demos/demo.py 46.62.169.221 demo1 demo2  # Multiple
python demos/demo.py 46.62.169.221              # All demos
```

### Auto-Discovery

New demos are automatically discovered if they have a `demo-script.py`.

## Creating a New Demo

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

3. Add sample application files

4. Test: `python demos/demo.py <server_ip> demo3`

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

## Available Demos

| Demo | Description | Hostname |
|------|-------------|----------|
| demo1 | uWSGI deployment (Python/Flask) | a1.hop.demo |
| demo2 | Docker deployment | a2.hop.demo |

## Usage Examples

```bash
# Run all demos
python demos/demo.py 46.62.169.221

# Single demo with local code
python demos/demo.py 46.62.169.221 demo1 --local

# Keep apps running for debugging
python demos/demo.py 46.62.169.221 demo2 --no-cleanup

# Screencast with longer pauses
python demos/demo.py 46.62.169.221 --pause 2
```
