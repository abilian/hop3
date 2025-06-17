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

1.  **Log in to your Hop3 Server:**
    Open your terminal and use the `hop3 login` command. Replace `hop3.example.com` with your server's hostname.

    ```bash
    hop3 login --server hop3.example.com
    # You will be prompted for your credentials.
    ```

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

Hop3 provides commands to manage your running application. Here are a few essential ones:

#### Check Application Status
To see the status of your app and its running processes:
```bash
hop3 status hello-hop3
```

#### View Live Logs
To see a real-time stream of your application's logs, which is incredibly useful for debugging:
```bash
hop3 logs hello-hop3
```
Press `Ctrl+C` to stop streaming.

#### Destroy the Application
If you want to remove the application and all its associated resources:
```bash
hop3 destroy hello-hop3
```

## Congratulations!

You have successfully deployed and managed your first application on Hop3. You can now use this workflow to deploy your own, more complex applications. Explore the rest of the documentation to learn about advanced features like managing environment variables, connecting to databases, and more.
