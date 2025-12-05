# Hop3 Demo Script Plan

## Overview

This demo script automates the complete Hop3 installation and quickstart workflow on a blank Ubuntu server. It's designed to be used for generating screencasts, with clear on-screen messages explaining each step.

## Target Audience

- Developers evaluating Hop3
- Users following along with documentation
- Marketing/documentation team creating screencasts

## Prerequisites

- A blank Ubuntu 22.04 server with SSH root access
- Local machine with Python 3.10+ and the Hop3 CLI installed
- SSH key authentication configured for the target server

## Demo Flow

### Phase 1: Installation (on remote server)

1. **Connect to server** - Verify SSH access
2. **Clone Hop3 repository** - From GitHub devel branch
3. **Install system dependencies** - apt packages
4. **Install Hop3** - Using pyinfra installer
5. **Run hop-server setup** - Initialize directories and config
6. **Restart hop3 service** - Apply configuration

### Phase 2: CLI Configuration (local)

1. **Create admin user** - Using `hop3 init --ssh`
2. **Verify connection** - Using `hop3 auth:whoami`

### Phase 3: Deploy Sample App

1. **Create sample Flask app** - hello-hop3 directory
2. **Deploy to server** - Using `hop3 deploy`
3. **Verify deployment** - Check app status
4. **Test the app** - HTTP request to verify response

### Phase 4: App Management Demo

1. **List apps** - `hop3 apps`
2. **Check status** - `hop3 app:status`
3. **View logs** - `hop3 app:logs`
4. **Set environment variables** - `hop3 config:set`
5. **Restart app** - `hop3 app:restart`

### Phase 5: Cleanup (optional)

1. **Destroy app** - `hop3 app:destroy`

## Script Structure

```
demo/
├── PLAN.md              # This file
├── demo.py              # Main demo script
└── hello-hop3/          # Sample application
    ├── app.py           # Flask application
    ├── requirements.txt # Python dependencies
    └── hop3.toml        # Hop3 configuration
```

## Key Design Decisions

1. **Screencast-friendly**: Each step displays a clear message before execution
2. **Modular functions**: Each phase is a separate function for clarity
3. **Echo commands**: Commands are printed before being executed
4. **Pause points**: Optional pauses between steps for narration
5. **Error handling**: Clear error messages if something fails
6. **Parameterized**: Server IP is a command-line argument

## Usage

```bash
# Basic usage
python demo.py 46.62.169.221

# With custom admin credentials
python demo.py 46.62.169.221 --admin-user admin --admin-email admin@example.com

# Skip installation (if already done)
python demo.py 46.62.169.221 --skip-install

# Skip cleanup at the end
python demo.py 46.62.169.221 --no-cleanup
```

## Output Style

The script uses colored output and clear section headers:

```
╔════════════════════════════════════════════════════════════════╗
║  STEP 1: Installing Hop3 on the server                         ║
╚════════════════════════════════════════════════════════════════╝

→ Cloning Hop3 repository from GitHub...

  $ git clone -b devel https://github.com/abilian/hop3.git

✓ Repository cloned successfully

→ Installing system dependencies...
```

## Notes

- The script uses subprocess for local commands and SSH for remote commands
- Admin password is generated randomly for security (or can be provided)
- The demo assumes the server has no prior Hop3 installation
- For screencasts, consider using `asciinema` to record the session
