# Hop3 Demo System

## Overview

A unified demo system for showcasing Hop3 features. Supports multiple demos that can be run individually or in sequence, with development mode for testing local code changes.

## Target Audience

- Developers evaluating Hop3
- Users following along with documentation
- Marketing/documentation team creating screencasts
- Hop3 developers testing changes
- CI/CD pipelines for automated testing

## Architecture

The demo system is a proper Python package with relative imports.

```
demos/
├── __init__.py         # Package marker
├── demo.py             # Entry point (~240 lines) - orchestration only
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
├── demo1/
│   ├── demo-script.py  # Demo metadata + run() function
│   └── hello-hop3/     # Sample Flask app
├── demo2/
│   ├── demo-script.py  # Demo metadata + run() function
│   └── hello-docker/   # Sample Docker app
└── demo3-9/            # Symlinks to apps/test-apps/
```

Run from the repository root: `python -m demos.demo`

## Command-Line Interface

### Synopsis

```
# Run demos
python -m demos.demo --host HOST [options] [demos...]

# Information (no --host required)
python -m demos.demo --help
python -m demos.demo --list [--demo-dir DIR]
python -m demos.demo --inventory [--demo-dir DIR]
```

### Complete Help Output

```
usage: python -m demos.demo --host HOST [options] [demos...]
       python -m demos.demo --list [--demo-dir DIR]
       python -m demos.demo --inventory [--demo-dir DIR]
       python -m demos.demo --help

Hop3 Demo Launcher - Interactive demonstrations of Hop3 deployment features.

This tool runs demos that showcase Hop3 capabilities. Each demo deploys a
sample application, tests it, and demonstrates lifecycle management.

Required (for running demos):
  -H, --host HOST          Target server IP address

Demo Selection:
  -d, --demo-dir DIR       Additional directory to search for demos
  demos...                 Demo name(s) or path(s) to run (default: all)

Server Options:
  --ssh-user USER          SSH user for server connection (default: root)
  --skip-install           Skip Hop3 installation and update
  -l, --local              Sync local hop3-server code via rsync

Authentication:
  --admin-user USER        Admin username to create (default: admin)
  --admin-email EMAIL      Admin email address (default: admin@example.com)
  --admin-password PWD     Admin password (auto-generated if not specified)

Demo Execution:
  -k, --keep               Keep deployed apps running after demo completes
  -p, --pause SECS         Pause between demo steps in seconds (default: 0.5)

Output Control:
  -q, --quiet              Reduced output (phases and results only)
  -s, --silent             No output except errors (for CI/CD)
  -v, --verbose            Show detailed output and stack traces

Information:
  -h, --help               Show this help message and exit
  --list                   List available demos (names and titles)
  --inventory              Show detailed inventory of all demos

Demos:
  Specify one or more demos to run. If none specified, runs all built-in demos.

  Built-in demos (in demos/ directory):
    demo1                  uWSGI deployment (Python/Flask)
    demo2                  Docker deployment
    demo3                  Static site (Nginx)
    ...

  You can also specify:
    - External paths: ~/my-project or /path/to/demo
      (runs demo-script.py if present, otherwise runs generic demo)
    - 'all': Explicitly run all built-in demos

Examples:
  # Run all demos
  python demo.py --host 46.62.169.221

  # Run specific demo
  python demo.py --host 46.62.169.221 demo1

  # Development: test local code changes
  python demo.py --host 46.62.169.221 -l demo1

  # Keep apps running for debugging
  python demo.py --host 46.62.169.221 -k demo2

  # CI/CD: silent mode, fail fast
  python demo.py --host 46.62.169.221 -s demo1 demo2

  # Use demos from custom directory
  python demo.py --host 46.62.169.221 -d ~/my-demos

  # Show detailed inventory
  python demo.py --inventory

  # Screencast: longer pauses, keep running
  python demo.py --host 46.62.169.221 -p 2 -k
```

### Option Reference

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--host HOST` | `-H` | (required) | Target server IP address |
| `--demo-dir DIR` | `-d` | | Additional directory to search for demos |
| `--ssh-user USER` | | `root` | SSH user for server connection |
| `--skip-install` | | false | Skip Hop3 installation and update |
| `--local` | `-l` | false | Use local code via rsync |
| `--admin-user USER` | | `admin` | Admin username to create |
| `--admin-email EMAIL` | | `admin@example.com` | Admin email address |
| `--admin-password PWD` | | (random) | Admin password |
| `--keep` | `-k` | false | Don't destroy apps after demo |
| `--pause SECS` | `-p` | `0.5` | Pause between steps |
| `--quiet` | `-q` | false | Reduced output |
| `--silent` | `-s` | false | No output except errors |
| `--verbose` | `-v` | false | Verbose output |
| `--help` | `-h` | | Show help and exit |
| `--list` | | | List available demos |
| `--inventory` | | | Show detailed demo inventory |

### Output Modes

| Mode | Flag | Description | Use Case |
|------|------|-------------|----------|
| **Normal** | (default) | Full step-by-step output with colors | Interactive use |
| **Quiet** | `-q` | Phase headers + pass/fail results only | Quick runs |
| **Silent** | `-s` | No output (errors to stderr) | CI/CD pipelines |
| **Verbose** | `-v` | Extra details + stack traces on error | Debugging |

### Demo Selection

Demo arguments are positional and come after all options:

1. **Built-in demo names**: `demo1`, `demo2`, etc.
   - Auto-discovered from `demos/` subdirectories containing `demo-script.py`

2. **External demo directory demos** (with `--demo-dir`):
   - Discovered from the specified directory

3. **External paths**: `~/my-project`, `/path/to/demo`
   - If `demo-script.py` exists: runs custom demo script
   - If no `demo-script.py`: runs **generic demo** (deploy, test, cleanup)
   - Supports `~` expansion and relative paths

4. **Keyword `all`**: Run all discovered demos
   - Case-insensitive (`all`, `ALL`, `All`)
   - Includes built-in + demos from `--demo-dir`

5. **Default**: If no demos specified, equivalent to `all`

### Information Commands

#### `--list`

Shows available demos (names and titles):

```
$ python demo.py --list

Available demos:

  demo1         Demo 1: uWSGI Deployment
  demo2         Demo 2: Docker Deployment
  demo3         Demo 3: Static Site
  demo4         Demo 4: Node.js Express
  demo5         Demo 5: Go with Gin
  demo6         Demo 6: Ruby Sinatra
  demo7         Demo 7: Flask + Gunicorn
  demo8         Demo 8: Python Poetry
  demo9         Demo 9: Minimal Go

You can also specify external paths to Hop3 applications.
```

#### `--inventory`

Shows detailed information about each demo:

```
$ python demo.py --inventory

Demo Inventory
==============

demo1 - Demo 1: uWSGI Deployment
  Location:  demos/demo1/hello-hop3
  App name:  hello-hop3
  Hostname:  a1.hop.demo
  Type:      Python (uWSGI)
  Files:     app.py, requirements.txt, hop3.toml

demo2 - Demo 2: Docker Deployment
  Location:  demos/demo2/hello-docker
  App name:  hello-docker
  Hostname:  a2.hop.demo
  Type:      Docker
  Files:     app.py, Dockerfile, hop3.toml

demo3 - Demo 3: Static Site
  Location:  demos/demo3/static-site -> apps/test-apps/000-static
  App name:  static-site
  Hostname:  a3.hop.demo
  Type:      Static
  Files:     Procfile, public/index.html

...

Total: 9 demos
```

With `--demo-dir`:

```
$ python demo.py --inventory --demo-dir ~/my-demos

Demo Inventory
==============

Built-in demos (demos/):
  demo1 - Demo 1: uWSGI Deployment
  ...

External demos (~/my-demos/):
  myapp1 - My Custom App
    Location:  ~/my-demos/myapp1
    App name:  my-custom-app
    ...

Total: 11 demos (9 built-in, 2 external)
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All demos completed successfully |
| 1 | One or more demos failed |
| 2 | Invalid arguments or missing required options |
| 130 | Interrupted by user (Ctrl+C) |

### Enhanced Summary Output

At the end of a multi-demo run, show detailed results:

```
╔════════════════════════════════════════════════════════════════════╗
║  Demo Summary                                                       ║
╚════════════════════════════════════════════════════════════════════╝

  [PASS] demo1 - Demo 1: uWSGI Deployment           (12.3s)
  [PASS] demo2 - Demo 2: Docker Deployment          (18.7s)
  [FAIL] demo3 - Demo 3: Static Site                (5.2s)
         └─ Error: Application not accessible at https://a3.hop.demo
  [PASS] demo4 - Demo 4: Node.js Express            (14.1s)
  [SKIP] demo5 - Demo 5: Go with Gin                (0.0s)
         └─ Skipped: Go toolchain not installed

─────────────────────────────────────────────────────────────────────
Results: 3 passed, 1 failed, 1 skipped
Duration: 50.3s

Admin credentials (apps kept running):
  Username: admin
  Password: xK7mN2pQ9...
```

In quiet mode (`-q`):

```
[PASS] demo1 (12.3s)
[PASS] demo2 (18.7s)
[FAIL] demo3 (5.2s) - Application not accessible
[PASS] demo4 (14.1s)

3/4 passed (45.3s)
```

In silent mode (`-s`): No output on success, only errors to stderr.

## Demo Flow

### Phase 1: Prerequisites

1. Verify SSH access to server
2. Check Ubuntu version (22.04 or 24.04)
3. Check if Hop3 is installed
4. Install or update Hop3 (supports `--local` for dev mode)
   - Skipped entirely with `--skip-install`

### Phase 2: CLI Configuration

1. Check hop3 CLI availability
2. Create admin user via SSH (or login if exists)
3. Verify authentication

### Phase 3: Run Selected Demos

For each demo:
1. Record start time
2. Run demo (custom script or generic)
3. Record end time and result
4. Continue to next demo (don't stop on failure)

### Phase 4: Summary

1. Show pass/fail/skip for each demo with timing
2. Show error messages for failures
3. Show total duration
4. Show credentials if `--keep` was used

## Key Features

### Development Mode (`--local`)

Syncs local hop3-server code to server via rsync:
```bash
python -m demos.demo --host 46.62.169.221 --local demo1
```

This allows testing changes without committing/pushing.

### Multi-Demo Support

Run demos individually or in sequence:
```bash
python -m demos.demo --host 46.62.169.221 demo1           # Single demo
python -m demos.demo --host 46.62.169.221 demo1 demo2     # Multiple
python -m demos.demo --host 46.62.169.221                 # All demos
```

### Custom Demo Directory (`--demo-dir`)

Load demos from an external directory:
```bash
# Use demos from custom directory alongside built-in
python -m demos.demo --host 46.62.169.221 --demo-dir ~/my-demos

# Run specific demo from custom directory
python -m demos.demo --host 46.62.169.221 --demo-dir ~/my-demos myapp

# Show inventory including custom directory
python -m demos.demo --inventory --demo-dir ~/my-demos
```

The demo directory structure should match the built-in demos:
```
~/my-demos/
├── myapp1/
│   ├── demo-script.py
│   └── app/
└── myapp2/
    ├── demo-script.py
    └── app/
```

### External Demos (Direct Paths)

Run demos from any directory:
```bash
python -m demos.demo --host 46.62.169.221 ~/my-project
python -m demos.demo --host 46.62.169.221 /tmp/test-demo
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

### CI/CD Mode (`--silent`)

For automated testing pipelines:
```bash
# Run all demos silently, fail on any error
python -m demos.demo --host $TEST_SERVER -s || exit 1

# Run specific demos with no output
python -m demos.demo --host $TEST_SERVER -s demo1 demo2 demo3
```

Exit code indicates success (0) or failure (non-zero).

### Auto-Discovery

Built-in demos are automatically discovered from subdirectories of `demos/` that contain a `demo-script.py` file.

## Creating a New Demo

### Built-in Demo

1. Create directory: `demos/demo10/`

2. Create `demo-script.py`:
```python
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

TITLE = "Demo 10: My Feature"
DESCRIPTION = "What this demo showcases"

APP_NAME = "my-app"
APP_DIR = Path(__file__).parent / "my-app"
DEFAULT_HOSTNAME = "a10.hop.demo"

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

3. Add sample application files in `demos/demo10/my-app/`

4. Test: `python -m demos.demo --host <server_ip> demo10`

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

Run with: `python -m demos.demo --host <server_ip> ~/my-project`

### External Demo (Generic / No Script)

Just point to any Hop3-compatible application directory:
```
~/my-flask-app/
├── app.py
├── requirements.txt
└── hop3.toml
```

Run with: `python -m demos.demo --host <server_ip> ~/my-flask-app`

The generic demo will:
- Use `my-flask-app` as the app name
- Deploy, configure hostname, test, and cleanup automatically

## Output Styles

### Normal Mode (default)

```
╔════════════════════════════════════════════════════════════════════╗
║  Phase 1: Prerequisites                                            ║
╚════════════════════════════════════════════════════════════════════╝

→ Verifying SSH access to the server...
✓ Connected to 46.62.169.221

→ Checking Ubuntu version...
✓ Ubuntu 24.04 LTS detected
```

### Quiet Mode (`-q`)

```
Phase 1: Prerequisites... OK
Phase 2: CLI Configuration... OK
[PASS] demo1 (12.3s)
[PASS] demo2 (18.7s)
2/2 passed (31.0s)
```

### Silent Mode (`-s`)

No output on success. On failure:
```
Error: demo3 failed - Application not accessible at https://a3.hop.demo
```

## Available Built-in Demos

| Demo | Description | App Hostname |
|------|-------------|--------------|
| demo1 | uWSGI deployment (Python/Flask) | a1.hop.demo |
| demo2 | Docker deployment | a2.hop.demo |
| demo3 | Static site (Nginx) | a3.hop.demo |
| demo4 | Node.js Express | a4.hop.demo |
| demo5 | Go with Gin framework | a5.hop.demo |
| demo6 | Ruby Sinatra | a6.hop.demo |
| demo7 | Flask + Gunicorn | a7.hop.demo |
| demo8 | Python Poetry project | a8.hop.demo |
| demo9 | Minimal Go (stdlib only) | a9.hop.demo |

Note: demo3-demo9 use symlinks to test apps in `apps/test-apps/`.

## Quick Reference

```bash
# Basic usage
python -m demos.demo --host 46.62.169.221

# Development workflow
python -m demos.demo --host 46.62.169.221 --local demo1

# Debugging (keep apps running)
python -m demos.demo --host 46.62.169.221 --keep demo2

# CI/CD (silent, all demos)
python -m demos.demo --host 46.62.169.221 --silent

# Screencast recording
python -m demos.demo --host 46.62.169.221 --pause 2 --keep

# External project
python -m demos.demo --host 46.62.169.221 ~/my-project --keep

# Custom demo directory
python -m demos.demo --host 46.62.169.221 --demo-dir ~/my-demos

# List available demos
python -m demos.demo --list

# Show detailed inventory
python -m demos.demo --inventory

# Help
python -m demos.demo --help
```

## Implementation Notes

### DemoResult Dataclass

```python
@dataclass
class DemoResult:
    name: str
    title: str
    status: Literal["pass", "fail", "skip"]
    duration: float  # seconds
    error: str | None = None
```

### Output Verbosity Levels

```python
class OutputLevel(Enum):
    SILENT = 0   # No output (errors to stderr)
    QUIET = 1    # Minimal output
    NORMAL = 2   # Default
    VERBOSE = 3  # Extra details
```

### Demo Info Extraction

For `--inventory`, extract from demo-script.py:
- `TITLE` - Demo title
- `DESCRIPTION` - Demo description
- `APP_NAME` - Application name
- `APP_DIR` - Application directory
- `DEFAULT_HOSTNAME` - Default hostname

Also detect from app directory:
- App type (Python, Node.js, Go, Ruby, Docker, Static)
- Key files present
- hop3.toml contents if available
