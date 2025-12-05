# Hop3 Demo

This directory contains a demo script that automates the complete Hop3 installation and quickstart workflow on a blank Ubuntu server.

## Purpose

The demo is designed to:

1. Install Hop3 on a fresh Ubuntu 22.04 server
2. Configure the CLI and create an admin user
3. Deploy a sample Flask application
4. Demonstrate application management commands
5. (Optionally) Clean up the demo application

It's ideal for generating screencasts or walking through the Hop3 experience.

## Prerequisites

- **Target Server**: A blank Ubuntu 22.04 server with SSH root access
- **Local Machine**:
  - Python 3.10+
  - Hop3 CLI installed (`pip install hop3-cli`)
  - SSH key authentication configured for the target server

## Usage

### Basic Usage

```bash
python demo.py <server_ip>
```

Example:
```bash
python demo.py 46.62.169.221
```

### Options

```bash
python demo.py <server_ip> [options]

Options:
  --ssh-user USER       SSH user (default: root)
  --admin-user USER     Admin username to create (default: admin)
  --admin-email EMAIL   Admin email (default: admin@example.com)
  --admin-password PWD  Admin password (default: randomly generated)
  --skip-install        Skip installation (Hop3 already installed)
  --no-cleanup          Don't destroy the demo app at the end
  --pause SECONDS       Pause between steps (default: 0.5)
```

### Examples

```bash
# Full demo from scratch
python demo.py 46.62.169.221

# Skip installation (Hop3 already installed)
python demo.py 46.62.169.221 --skip-install

# Keep the demo app running after the demo
python demo.py 46.62.169.221 --no-cleanup

# Custom admin credentials
python demo.py 46.62.169.221 --admin-user myuser --admin-email me@example.com

# Slower pacing for screencasts
python demo.py 46.62.169.221 --pause 2
```

## Recording a Screencast

For best results with `asciinema`:

```bash
# Start recording
asciinema rec hop3-demo.cast

# Run the demo with longer pauses
python demo.py 46.62.169.221 --pause 2 --no-cleanup

# Stop recording with Ctrl+D
```

## Files

```
demo/
├── README.md           # This file
├── PLAN.md             # Detailed plan and design document
├── demo.py             # Main demo script
└── hello-hop3/         # Sample Flask application
    ├── app.py          # Flask application code
    ├── requirements.txt # Python dependencies
    └── hop3.toml       # Hop3 configuration
```

## Troubleshooting

### SSH Connection Issues

Ensure you can connect without password:
```bash
ssh root@<server_ip> echo "Connected"
```

If this fails, set up SSH key authentication:
```bash
ssh-copy-id root@<server_ip>
```

### hop3 CLI Not Found

Install the Hop3 CLI:
```bash
pip install hop3-cli
```

Or from the repository:
```bash
cd packages/hop3-cli
pip install -e .
```

### Installation Takes Too Long

The initial installation can take 5-10 minutes as it:
- Updates system packages
- Installs Python, nginx, uwsgi, and other dependencies
- Configures the hop3 user and services

Use `--skip-install` if Hop3 is already installed.
