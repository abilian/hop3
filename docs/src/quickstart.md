# Hop3 Quick Start: Deploying Your First Application

This guide will walk you through deploying your first web application from scratch. We will create a simple Python Flask application, configure it for Hop3, and deploy it to your server.

By the end of this tutorial, you will have a live, running web application managed by Hop3.

## Prerequisites

Before you begin, you must have the following:

1.  **A Server with Hop3 Installed:** You need a server (or VM) with a fresh installation of Hop3. If you haven't done this yet, follow the [**Hop3 Installer Guide**](./installation.md) first.
2.  **The Hop3 CLI on Your Local Machine:** The `hop3` command-line tool should be installed locally. The installation guide covers setting up the development environment, which includes the CLI.

## Step 1: Create a Sample Python Application

First, let's create a simple "Hello World" application using the Flask framework. On your local machine, create a new directory for your project.

```bash
mkdir hello-hop3
cd hello-hop3
```

Inside this directory, create two files: `app.py` and `requirements.txt`.

#### `app.py`

This file contains the code for our web application.

```python
# app.py
import os
from flask import Flask

app = Flask(__name__)

# Hop3 will set the PORT environment variable to tell our app what port to listen on.
port = int(os.environ.get("PORT", 5000))

@app.route('/')
def hello_world():
    return '<h1>Hello, Hop3!</h1><p>Your Flask application is running.</p>'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port)
```

#### `requirements.txt`

This file lists the Python dependencies our application needs. Hop3 will use this to install the necessary packages.

```
# requirements.txt
Flask
gunicorn
```
We include `gunicorn` as it is a production-grade WSGI server that Hop3 will use to run our application.

## Step 2: Configure the Application for Hop3

Now, we need to tell Hop3 how to build and run our application. We do this by creating a `hop3.toml` file in the root of our project directory.

Create the `hop3.toml` file with the following content:

```toml
# hop3.toml

# The [metadata] section is mandatory. It describes your application.
[metadata]
id = "hello-hop3"
version = "0.1.0"
title = "Hello Hop3 App"
author = "A Hop3 User"
description = "A simple Flask application to demonstrate Hop3 deployment."

# The [build] section tells Hop3 how to prepare your application.
[build]
# We specify the Python builder and tell it to install packages from requirements.txt
builder = "python-3.10"
pip-install = ["-r", "requirements.txt"]

# The [run] section specifies the command to start your application.
[run]
start = "gunicorn --workers 2 --bind 0.0.0.0:$PORT app:app"

# The [port] section declares which internal port should be exposed to the web.
[port.web]
container = 5000 # This should match the port gunicorn listens on if PORT isn't set.
public = true
```

!!! note "What does this file do?"
    - **`[metadata]`**: Provides essential information like a unique `id` for your app.
    - **`[build]`**: Instructs Hop3 to use a Python environment and install the dependencies listed in `requirements.txt`.
    - **`[run]`**: Defines the command that starts the web server. Hop3 automatically provides the `$PORT` environment variable.
    - **`[port.web]`**: Tells Hop3's internal router (Nginx) that the application process listening on its container port should be made publicly accessible via HTTP/HTTPS.

## Step 3: Deploy to Hop3

With your application code and configuration ready, you can now deploy it.

1.  **Configure your CLI (first time only):**

    If this is your first time using Hop3, you need to create an admin user and configure your CLI. The easiest way is:

    ```bash
    hop3 init --ssh root@hop3.example.com
    ```

    This will prompt you for admin credentials and automatically save your API token.

    If you've already set up the server and just need to configure a new machine:

    ```bash
    hop3 login --ssh root@hop3.example.com
    ```

    See the [Installation Guide](./installation.md) for detailed setup instructions.

2.  **Deploy the Application:**
    From inside your `hello-hop3` project directory, run the deploy command:

    ```bash
    hop3 deploy
    ```

    You will see output from Hop3 as it:
    -   Uploads your application code.
    -   Builds the application environment and installs dependencies.
    -   Starts the application process.
    -   Configures the router to direct traffic to your app.

## Step 4: Verify Your Deployment

Once the deployment is complete, Hop3 will provide you with the URL for your application. It will typically be in the format `http://<app-id>.<your-hop3-host>`.

Open your web browser and navigate to the URL. For our example, it would be something like:

**`http://hello-hop3.hop3.example.com`**

You should see the "Hello, Hop3!" message from your Flask application.

## Step 5: Managing Your App

Hop3 provides commands to manage your running application. The CLI features rich, colorful output to make information easy to read and understand.

#### Check Application Status
To see the status of your app and its running processes:
```bash
hop3 app:status hello-hop3
```

You'll see a nicely formatted table showing:
```
┏━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┓
┃ Application ┃ Status   ┃ Processes ┃ URL             ┃
┡━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━┩
│ hello-hop3  │ RUNNING  │ web: 2    │ hello-hop3.hop3 │
│             │          │           │ .example.com    │
└─────────────┴──────────┴───────────┴─────────────────┘
```

**For automation and scripts**, use JSON output:
```bash
hop3 app:status hello-hop3 --json
```
```json
{
  "status": "success",
  "data": {
    "name": "hello-hop3",
    "state": "RUNNING",
    "processes": {"web": 2},
    "url": "hello-hop3.hop3.example.com"
  }
}
```

#### View Live Logs
To see a real-time stream of your application's logs, which is incredibly useful for debugging:
```bash
hop3 app:logs hello-hop3
```
Press `Ctrl+C` to stop streaming.

#### List All Applications
See all your deployed applications at a glance:
```bash
hop3 apps
```

#### Destroy the Application
If you want to remove the application and all its associated resources:
```bash
hop3 app:destroy hello-hop3
```

⚠️ **Destructive commands require confirmation.** To prevent accidental deletion, you'll be prompted:
```
WARNING: This will permanently delete the app 'hello-hop3' and all its data.
Type the app name to confirm: hello-hop3
```

**To skip confirmations in scripts**, use the `-y` flag:
```bash
hop3 app:destroy hello-hop3 -y
```

!!! tip "Quiet Output for Scripts"
    When writing automation scripts, use `--quiet` to suppress unnecessary output:
    ```bash
    hop3 deploy --quiet
    hop3 app:status myapp --json --quiet
    ```

## Step 6: Backup and Restore

Hop3 provides a powerful backup and restore system to protect your applications and data. This is essential for production deployments.

### Create a Backup

Before making changes to your application, it's always a good idea to create a backup:

```bash
hop3 backup:create hello-hop3
```

This creates a complete backup including:
- Source code (git repository)
- Application data
- Environment variables
- Any attached services (databases, etc.)

You'll see rich formatted output like:

```
╭──────────────────────────────────────────────────────────────╮
│                Creating Backup for 'hello-hop3'              │
╰──────────────────────────────────────────────────────────────╯

✓ Backing up source code (git repository)
✓ Backing up application data
✓ Backing up environment variables
✓ Backing up service configurations

╭──────────────────────────────────────────────────────────────╮
│                   Backup Created Successfully                │
╰──────────────────────────────────────────────────────────────╯

Backup ID:  20251108_143022_a8f3d9
Location:   /var/hop3/backups/apps/hello-hop3/20251108_143022_a8f3d9
Total size: 2.3 MB
Duration:   1.2s

To restore this backup:
  hop3 backup:restore 20251108_143022_a8f3d9
```

### List Your Backups

To see all backups for your application:

```bash
hop3 backup:list hello-hop3
```

You'll see a table with all available backups:
```
┏━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┓
┃ Backup ID             ┃ Application ┃ Size    ┃ Created             ┃
┡━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━┩
│ 20251108_143022_a8f3d9│ hello-hop3  │ 2.3 MB  │ 2025-11-08 14:30:22 │
│ 20251107_091534_f2e1b7│ hello-hop3  │ 2.1 MB  │ 2025-11-07 09:15:34 │
│ 20251106_183245_d9c4a2│ hello-hop3  │ 2.0 MB  │ 2025-11-06 18:32:45 │
└───────────────────────┴─────────────┴─────────┴─────────────────────┘
```

Or list all backups across all applications:

```bash
hop3 backup:list
```

**For scripting**, use JSON output:
```bash
hop3 backup:list hello-hop3 --json
```

### Restore from Backup

If something goes wrong, you can restore your application to a previous state:

```bash
hop3 backup:restore 20251108_143022_a8f3d9
hop3 app:restart hello-hop3
```

This restores:
- All source code to the exact state at backup time
- Application data files
- Environment variables
- Service configurations

!!! tip "Best Practice: Backup Before Deployment"
    Get in the habit of creating a backup before each deployment:
    ```bash
    # Create backup
    hop3 backup:create hello-hop3

    # Deploy new version
    hop3 deploy

    # If something goes wrong, restore
    hop3 backup:restore <backup-id>
    hop3 app:restart hello-hop3
    ```

For complete backup documentation, see the [**Backup and Restore Guide**](backup-restore.md).

## Step 7: Working with Environment Variables

Applications often need configuration through environment variables. Hop3 makes this easy with intuitive commands.

#### Setting Environment Variables

Set a single environment variable:
```bash
hop3 config:set hello-hop3 DEBUG=true
```

Set multiple variables at once:
```bash
hop3 config:set hello-hop3 DEBUG=true LOG_LEVEL=info MAX_WORKERS=4
```

#### Viewing Environment Variables

List all environment variables for your app:
```bash
hop3 config:show hello-hop3
```

You'll see a formatted table:
```
┏━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━┓
┃ Variable    ┃ Value             ┃
┡━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━┩
│ PORT        │ 5000              │
│ DEBUG       │ true              │
│ LOG_LEVEL   │ info              │
│ MAX_WORKERS │ 4                 │
└─────────────┴───────────────────┘
```

Get a specific variable's value:
```bash
hop3 config:get hello-hop3 DEBUG
```

**For scripts**, use JSON output:
```bash
hop3 config:show hello-hop3 --json
```
```json
{
  "status": "success",
  "data": {
    "PORT": "5000",
    "DEBUG": "true",
    "LOG_LEVEL": "info",
    "MAX_WORKERS": "4"
  }
}
```

#### Removing Environment Variables

Remove a variable:
```bash
hop3 config:unset hello-hop3 DEBUG
```

!!! note "Restart Required"
    After changing environment variables, restart your app for the changes to take effect:
    ```bash
    hop3 app:restart hello-hop3
    ```

## Advanced CLI Features

### JSON Output for Automation

Almost all Hop3 commands support `--json` output for scripting and automation:

```bash
# Get app status in JSON
hop3 app:status myapp --json | jq '.data.state'

# List all apps and filter by status
hop3 app:list --json | jq '.data[] | select(.state == "RUNNING")'

# Create backup and capture backup ID
BACKUP_ID=$(hop3 backup:create myapp --json | jq -r '.data.backup_id')
echo "Created backup: $BACKUP_ID"
```

### Quiet Mode for Scripts

Use `--quiet` to suppress progress messages and only show essential output:

```bash
# Silent deployment (only errors shown)
hop3 deploy --quiet

# Combine with JSON for clean machine-readable output
hop3 app:list --json --quiet
```

### Skipping Confirmations

For automation, skip confirmation prompts with `-y`:

```bash
# Automated cleanup script
hop3 app:destroy old-app -y
hop3 backup:delete old-backup-id -y
```

⚠️ **Use with caution** - the `-y` flag bypasses safety confirmations!

### Verbose Output for Debugging

Get detailed output with `-v` or `--verbose`:

```bash
hop3 deploy -v
hop3 app:status myapp --verbose
```

## Congratulations!

You have successfully deployed and managed your first application on Hop3. You can now use this workflow to deploy your own, more complex applications.

## Next Steps

- **[CLI Reference](cli-reference.md)** - Complete reference for all 62 Hop3 commands
- **[Backup and Restore Guide](backup-restore.md)** - Comprehensive backup documentation
- **[hop3.toml Reference](hop3-toml-reference.md)** - Complete configuration file reference
- **[Migration Guide](migration-guide.md)** - Migrate from Heroku, Fly.io, or other platforms

For help at any time, run:
```bash
hop3 help
hop3 <command> --help
```
