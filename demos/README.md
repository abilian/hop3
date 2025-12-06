# Hop3 Demos

Demo applications and scripts for showcasing Hop3 features.

## Quick Start

```bash
# Run all demos on a server
python demos/demo.py --host 46.62.169.221

# Run a specific demo
python demos/demo.py --host 46.62.169.221 demo1

# Run multiple demos
python demos/demo.py --host 46.62.169.221 demo1 demo2

# Run your own app
python demos/demo.py --host 46.62.169.221 ~/my-flask-app
```

Note: Run from the hop3 repository root directory.

## Available Demos

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

Use `python demos/demo.py --list` to see all available demos.

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
python demos/demo.py --host 46.62.169.221 --local demo1

# Keep apps running for debugging
python demos/demo.py --host 46.62.169.221 --local --keep demo2
```

The `--local` flag uses rsync to sync your local hop3-server code to the server.

### Recording Screencasts

```bash
# Longer pauses, keep apps visible
python demos/demo.py --host 46.62.169.221 --pause 2 --keep
```

### CI/CD Integration

```bash
# Minimal output for CI logs
python demos/demo.py --quiet --host 46.62.169.221 demo1

# Silent mode (errors to stderr only)
python demos/demo.py --silent --host 46.62.169.221 demo1

# Exit code: 0 = all passed, 1 = some failed
```

### Demo Inventory

```bash
# View detailed info about all demos
python demos/demo.py --inventory

# Include external demo directories
python demos/demo.py --inventory --demo-dir ~/my-demos
```

### External Applications

Run any Hop3-compatible application:

```bash
# Your app with hop3.toml, Dockerfile, or requirements.txt
python demos/demo.py --host 46.62.169.221 ~/my-project

# Keep it running after demo
python demos/demo.py --host 46.62.169.221 ~/my-project --keep
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
├── demo.py             # Entry point (~240 lines)
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
├── demo1/              # uWSGI (Flask)
├── demo2/              # Docker
├── demo3/              # Static site (symlink)
├── demo4/              # Node.js Express (symlink)
├── demo5/              # Go with Gin (symlink)
├── demo6/              # Ruby Sinatra (symlink)
├── demo7/              # Flask + Gunicorn (symlink)
├── demo8/              # Python Poetry (symlink)
└── demo9/              # Minimal Go (symlink)
```

Note: demo3-demo9 use symlinks to apps in `apps/test-apps/` to avoid duplication.

## Creating a New Demo

### Option 1: Custom Demo Script

1. Create directory: `demos/demo3/`
2. Create `demo-script.py` with `TITLE`, `DESCRIPTION`, and `run(ctx)` function
3. Add sample application files
4. The demo is auto-discovered

### Option 2: Generic Demo (No Script Needed)

Just point to any Hop3-compatible application:

```bash
python demos/demo.py --host 46.62.169.221 ~/my-app
```

The generic demo will automatically:
- Detect app type (Python, Docker, Node.js, etc.)
- Deploy using the appropriate builder
- Set up hostname and proxy
- Test the deployment
- Clean up (unless `--keep`)
