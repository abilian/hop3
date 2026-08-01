# Hop3 Quick Start: Deploying Your First Application

This guide will walk you through deploying your first web application from scratch. We will create a simple Python Flask application, configure it for Hop3, and deploy it to your server.

By the end of this tutorial, you will have a live, running web application managed by Hop3.

## Prerequisites

Before you begin, you must have the following:

1.  **A Server with Hop3 Installed:** You need a server (or VM) with a fresh installation of Hop3. If you haven't done this yet, follow the [**Hop3 Installer Guide**](./server-setup.md) first.
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
# Use the local builder - Python toolchain is auto-detected from requirements.txt
builder = "local"

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
    hop3 auth login --ssh root@hop3.example.com
    ```

    See the [Installation Guide](./server-setup.md) for detailed setup instructions.

2.  **Deploy the Application:**
    From inside your `hello-hop3` project directory, run the deploy command:

    ```bash
    hop3 deploy --app hello-hop3
    ```

    When you run this from inside the project directory, Hop3 resolves the app from context, so a bare `hop3 deploy` works too.

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
hop3 app status --app hello-hop3
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
hop3 app status --app hello-hop3 --json
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

#### View Logs
To see your application's recent logs, which is useful for debugging:
```bash
hop3 app logs --app hello-hop3
```
This prints the last 100 lines by default. Use `-n`/`--lines` to change the count, `--grep PATTERN` to filter, `--since-deploy` to limit output to the latest deployment, or `--build` to show build output.

#### List All Applications
See all your deployed applications at a glance:
```bash
hop3 app list
```

#### Destroy the Application
If you want to remove the application and all its associated resources:
```bash
hop3 app destroy --app hello-hop3
```

⚠️ **Destructive commands require confirmation.** To prevent accidental deletion, you'll be prompted:
```
WARNING: This will permanently delete the app 'hello-hop3' and all its data.
Type the app name to confirm: hello-hop3
```

**To skip confirmations in scripts**, use the `-y` flag:
```bash
hop3 app destroy --app hello-hop3 -y
```

!!! tip "Quiet Output for Scripts"
    When writing automation scripts, use `--quiet` to suppress unnecessary output:
    ```bash
    hop3 deploy --app myapp --quiet
    hop3 app status --app myapp --json --quiet
    ```

## Step 6: Backup and Restore

Hop3 includes a backup system to protect your applications. Always backup before making significant changes.

```bash
# Create a backup (includes code, data, env vars, and attached services)
hop3 backup create --app hello-hop3

# List your backups
hop3 backup list hello-hop3

# Restore if needed
hop3 backup restore <backup-id>
hop3 app restart --app hello-hop3
```

!!! tip "Best Practice: Backup Before Deployment"
    ```bash
    hop3 backup create --app hello-hop3  # Create backup
    hop3 deploy --app hello-hop3         # Deploy new version
    # If something goes wrong:
    hop3 backup restore <backup-id>
    hop3 app restart --app hello-hop3
    ```

For complete backup documentation including what's backed up, retention policies, and troubleshooting, see the **[Backup and Restore Guide](../guides/backup-restore.md)**.

## Step 7: Working with Environment Variables

Applications often need configuration through environment variables. Hop3 makes this easy with intuitive commands.

#### Setting Environment Variables

Set a single environment variable:
```bash
hop3 env set --app hello-hop3 LOG_LEVEL=info
```

Set multiple variables at once:
```bash
hop3 env set --app hello-hop3 LOG_LEVEL=info MAX_WORKERS=4 SECRET_KEY=your-secret
```

!!! note "About DEBUG mode"
    Only set `DEBUG=true` in development environments for troubleshooting. Never enable DEBUG in production as it may expose sensitive information.

#### Viewing Environment Variables

List all environment variables for your app:
```bash
hop3 env show --app hello-hop3
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
hop3 env get --app hello-hop3 DEBUG
```

**For scripts**, use JSON output:
```bash
hop3 env show --app hello-hop3 --json
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
hop3 env unset --app hello-hop3 DEBUG
```

!!! note "Restart Required"
    After changing environment variables, restart your app for the changes to take effect:
    ```bash
    hop3 app restart --app hello-hop3
    ```

## Advanced CLI Features

### JSON Output for Automation

Almost all Hop3 commands support `--json` output for scripting and automation:

```bash
# Get app status in JSON
hop3 app status --app myapp --json | jq '.data.state'

# List all apps and filter by status
hop3 app list --json | jq '.data[] | select(.state == "RUNNING")'

# Create backup and capture backup ID
BACKUP_ID=$(hop3 backup create --app myapp --json | jq -r '.data.backup_id')
echo "Created backup: $BACKUP_ID"
```

### Quiet Mode for Scripts

Use `--quiet` to suppress progress messages and only show essential output:

```bash
# Silent deployment (only errors shown)
hop3 deploy --app myapp --quiet

# Combine with JSON for clean machine-readable output
hop3 app list --json --quiet
```

### Skipping Confirmations

For automation, skip confirmation prompts with `-y`:

```bash
# Automated cleanup script
hop3 app destroy --app old-app -y
hop3 backup destroy old-backup-id -y
```

⚠️ **Use with caution** - the `-y` flag bypasses safety confirmations!

### Verbose Output for Debugging

Get detailed output with `-v` or `--verbose`:

```bash
hop3 deploy --app myapp -v
hop3 app status --app myapp --verbose
```

## Congratulations!

You have successfully deployed and managed your first application on Hop3. You can now use this workflow to deploy your own, more complex applications.

## Next Steps

- **[CLI Reference](../reference/cli.md)** - Complete reference for all Hop3 commands
- **[Backup and Restore Guide](../guides/backup-restore.md)** - Comprehensive backup documentation
- **[hop3.toml Reference](../reference/config.md)** - Complete configuration file reference
- **[Migration Guide](../guides/migration-guide.md)** - Migrate from Heroku, Fly.io, or other platforms

For help at any time, run:
```bash
hop3 help
hop3 <command> --help
```
