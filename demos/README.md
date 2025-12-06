# Hop3 Demos

This directory contains demo scripts that automate Hop3 workflows for screencasts and tutorials.

## Available Demos

### Demo 1: Installation & Quickstart (uWSGI)

**Path:** `demo1/`

Demonstrates the complete Hop3 installation and quickstart workflow:
- Installing Hop3 on a fresh Ubuntu server
- Configuring the CLI and creating an admin user
- Deploying a sample Flask application (uWSGI-based)
- Application management commands

```bash
# Full installation + deployment
python demos/demo1/demo.py 46.62.169.221

# Skip installation (Hop3 already installed)
python demos/demo1/demo.py 46.62.169.221 --skip-install
```

### Demo 2: Docker Deployment

**Path:** `demo2/`

Demonstrates Docker-based deployment with Hop3:
- Building Docker images from Dockerfile
- Deploying containers with Docker Compose
- Routing traffic through nginx proxy to containers
- Managing Docker-based applications

**Prerequisite:** Requires Hop3 to be installed (run demo1 first on fresh servers).

```bash
python demos/demo2/demo.py 46.62.169.221
```

## Common Options

All demos support these common options:

| Option | Description |
|--------|-------------|
| `--ssh-user USER` | SSH user (default: root) |
| `--admin-user USER` | Admin username (default: admin) |
| `--admin-email EMAIL` | Admin email (default: admin@example.com) |
| `--admin-password PWD` | Admin password (default: randomly generated) |
| `--app-hostname HOST` | Hostname for the app (demo1: a1.hop.demo, demo2: a2.hop.demo) |
| `--no-cleanup` | Keep the app running after the demo |
| `--pause SECONDS` | Pause between steps (default: 0.5) |

## Recording Screencasts

For best results with `asciinema`:

```bash
# Start recording
asciinema rec hop3-demo.cast

# Run a demo with longer pauses
python demos/demo1/demo.py 46.62.169.221 --pause 2 --no-cleanup

# Stop recording with Ctrl+D
```

## Test Server Hostnames

For testing, these hostnames are pre-configured to point to the test server:

- `a1.hop.demo` - Demo 1 (uWSGI app)
- `a2.hop.demo` - Demo 2 (Docker app)
- `a3.hop.demo` - Reserved for future demos
- etc.

## Prerequisites

- **Target Server**: Ubuntu 22.04 or 24.04 with SSH root access
- **Local Machine**:
  - Python 3.10+
  - Hop3 CLI installed (`pip install hop3-cli`)
  - SSH key authentication configured
