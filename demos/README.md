# Hop3 Demos

Demo applications and scripts for showcasing Hop3 features.

## Quick Start

```bash
# Run all demos on a server
python demos/demo.py <server_ip>

# Run a specific demo
python demos/demo.py <server_ip> demo1

# Run multiple demos
python demos/demo.py <server_ip> demo1 demo2
```

## Available Demos

| Demo | Description | App Hostname |
|------|-------------|--------------|
| demo1 | uWSGI deployment (Python/Flask) | a1.hop.demo |
| demo2 | Docker deployment | a2.hop.demo |

## Options

```
python demos/demo.py <server_ip> [demo_names...] [options]

Options:
  --ssh-user USER        SSH user for the server (default: root)
  --admin-user USER      Admin username to create (default: admin)
  --admin-email EMAIL    Admin email (default: admin@example.com)
  --admin-password PWD   Admin password (default: randomly generated)
  --local                Use local code via rsync (for development)
  --skip-install         Skip Hop3 installation (assume already installed)
  --no-cleanup           Don't destroy demo apps at the end
  --pause SECONDS        Pause between steps (default: 0.5)
  --verbose, -v          Enable verbose output
```

## Development Mode

Test local code changes without committing:

```bash
# Sync local code to server and run demo
python demos/demo.py 46.62.169.221 demo1 --local

# Keep apps running for debugging
python demos/demo.py 46.62.169.221 demo2 --local --no-cleanup
```

The `--local` flag uses rsync to sync your local hop3-server code to the server.

## Prerequisites

- **Target Server**: Ubuntu 22.04 or 24.04 with SSH root access
- **Local Machine**:
  - Python 3.10+
  - Hop3 CLI installed (`pip install hop3-cli`)
  - SSH key authentication configured

## Recording Screencasts

```bash
asciinema rec hop3-demo.cast
python demos/demo.py 46.62.169.221 demo1 --pause 2 --no-cleanup
# Stop with Ctrl+D
```

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
├── demo.py           # Unified demo runner
├── lib/              # Shared utilities
│   ├── __init__.py
│   ├── app.py        # Common app management routines
│   ├── commands.py   # run_local, run_ssh, run_hop3
│   ├── context.py    # DemoContext dataclass
│   ├── output.py     # Terminal output helpers
│   └── server.py     # Server setup, sync, update
├── demo1/
│   ├── demo-script.py  # Demo logic
│   └── hello-hop3/     # Sample Flask app
└── demo2/
    ├── demo-script.py  # Demo logic
    └── hello-docker/   # Sample Docker app
```

## Creating a New Demo

1. Create directory: `demos/demo3/`
2. Create `demo-script.py` with `TITLE`, `DESCRIPTION`, and `run(ctx)` function
3. Add sample application files
4. The demo is auto-discovered
