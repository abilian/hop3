---
date: 2026-02-06
template: blog_post.html
description: Step-by-step tutorial for deploying a Flask app with database and custom domain.
tags:
  - Tutorial
  - Getting Started
---

# Your First Hop3 Deployment: From Zero to Production

Remember the first time you deployed something to Heroku? `git push heroku main` and suddenly your side project was live on the internet. That feeling of "wait, it just... works?" is what we're chasing with Hop3.

The difference: your code runs on your server, not someone else's cloud. Same simplicity, full control.

Let's deploy a Flask app from scratch. By the end of this post, you'll have a production-ready application with a database, custom domain, and SSL—all on a server you own.

## What You'll Need

- A server running Ubuntu 24.04+ or Debian 12+ (a $5/month VPS works fine)
- SSH access to that server
- A domain name (optional, but satisfying)

Don't have a server yet? Hetzner, Scaleway, DigitalOcean, Linode... can have you running in minutes. Hop3 isn't picky.

## Setting Up the Server

First, let's install Hop3 on your server. SSH in and run the installer:

```bash
ssh root@your-server.com
curl -LsSf https://hop3.cloud/install-server.py | sudo python3 -
```

Grab a coffee—this takes a few minutes. The installer creates a `hop3` user, installs Python, Node, nginx, and sets up the hop3-server service. When it finishes, you'll see a success message.

## Installing the CLI

Now switch to your **local machine**. The CLI is how you'll interact with your server:

```bash
pip install hop3-cli
# or if you prefer uv
uv tool install hop3-cli
```

Verify it works:

```bash
hop3 --version
```

## Connecting to Your Server

Tell the CLI where your server lives:

```bash
hop3 settings set server ssh://root@your-server.com
```

Test the connection:

```bash
hop3 apps list
```

You should see an empty list. That's about to change.

## Building a Flask App

Let's create something simple but real—an app that tracks page visits. Nothing fancy, but it'll exercise the full deployment pipeline.

```bash
mkdir myapp && cd myapp
```

Create `app.py`:

```python
from flask import Flask

app = Flask(__name__)

@app.route("/")
def hello():
    return "Hello from Hop3!"

@app.route("/health")
def health():
    return "OK"

if __name__ == "__main__":
    app.run()
```

Create `requirements.txt`:

```
flask>=3.0
gunicorn>=21.0
```

Create a `Procfile` (yes, like Heroku):

```
web: gunicorn app:app -b 0.0.0.0:$PORT
```

And a `hop3.toml` for Hop3-specific configuration:

```toml
[metadata]
id = "myapp"

[healthcheck]
path = "/health"
```

That's it. Four files, maybe 30 lines total.

## The Moment of Truth

Deploy:

```bash
hop3 deploy myapp
```

Watch the magic happen:

```
-> Uploading source (3 files, 1.2 KB)
-> Detecting toolchain: python (found requirements.txt)
-> Creating virtual environment...
-> Installing dependencies...
-> Starting application...
-> App deployed successfully!

URL: http://your-server.com:5000
```

Open that URL. See "Hello from Hop3!"? You just deployed an application. No Docker, no Kubernetes, no YAML files—just code to server.

## Adding Your Domain

Running on an IP address and port is fine for testing, but let's make this look professional.

Update `hop3.toml`:

```toml
[metadata]
id = "myapp"

[env]
HOST_NAME = "myapp.example.com"

[healthcheck]
path = "/health"
```

Point your DNS to the server:

```
myapp.example.com  A  your-server-ip
```

Redeploy:

```bash
hop3 deploy myapp
```

Hop3 automatically:
- Configures nginx with your domain
- Requests a Let's Encrypt SSL certificate
- Sets up HTTPS redirects

Visit `https://myapp.example.com`. That padlock icon? That's real SSL, automatically provisioned.

## Adding a Database

Most real apps need a database. Let's add PostgreSQL:

```bash
hop3 addons create postgres myapp-db
hop3 addons attach myapp myapp-db
```

Two commands. You now have a PostgreSQL database with `DATABASE_URL` automatically injected into your app's environment.

Let's use it. Update `app.py`:

```python
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
db = SQLAlchemy(app)

class Visit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=db.func.now())

@app.route("/")
def hello():
    visit = Visit()
    db.session.add(visit)
    db.session.commit()
    count = Visit.query.count()
    return f"Hello! Visit count: {count}"

@app.route("/health")
def health():
    return "OK"
```

Update `requirements.txt`:

```
flask>=3.0
gunicorn>=21.0
flask-sqlalchemy>=3.0
psycopg2-binary>=2.9
```

And tell Hop3 to create the database tables on deploy. Update `hop3.toml`:

```toml
[metadata]
id = "myapp"

[env]
HOST_NAME = "myapp.example.com"

[run]
before-run = "flask db upgrade"

[healthcheck]
path = "/health"
```

Redeploy:

```bash
hop3 deploy myapp
```

Refresh your browser. Each visit increments the counter. Your app now has persistent state.

## Day-to-Day Operations

Now that your app is running, here's how you'll interact with it:

**Check what's happening:**

```bash
hop3 app logs myapp      # Recent logs
hop3 app logs myapp -f   # Follow logs in real-time
```

**See your apps:**

```bash
hop3 apps list
```

```
NAME    STATUS   URL
myapp   running  https://myapp.example.com
```

**Get details:**

```bash
hop3 apps info myapp
```

```
App: myapp
Status: running
URL: https://myapp.example.com
Workers: 1 x web
Addons: myapp-db (postgres)
Last deployed: 2026-03-21 10:30:00
```

**Need more capacity?**

```bash
hop3 ps scale --app myapp web=3
```

Now three gunicorn workers handle requests. Scaling is just a number.

## When Things Go Wrong

They will. Here's how to debug.

**App won't start?** Check the logs:

```bash
hop3 app logs myapp
```

Common culprits:
- Missing dependency in `requirements.txt`
- Typo in `Procfile`
- Port not binding to `$PORT`

**502 Bad Gateway?** Nginx is running but can't reach your app:

```bash
hop3 run myapp "ss -tlnp"
```

Make sure you're binding to `0.0.0.0:$PORT`, not `127.0.0.1` or a hardcoded port.

**Database connection failed?** Check that the addon is attached:

```bash
hop3 config show --app myapp
```

Look for `DATABASE_URL` in the output.

## Quick Reference

Commands you'll use constantly:

```bash
hop3 deploy myapp              # Deploy changes
hop3 app logs myapp                # View logs
hop3 apps restart myapp        # Restart
hop3 apps stop myapp           # Stop
hop3 apps start myapp          # Start
hop3 apps destroy myapp        # Delete (careful!)
hop3 config set --app myapp KEY=val  # Set environment variable
hop3 config show --app myapp         # View configuration
```

## What's Next?

You've got a production application running. From here you might want to:

- Add background workers for async tasks
- Configure static file serving for CSS/JS
- Set up automated backups
- Add monitoring and alerting

Check our [guides](/guides/) for details on each of these.

---

That's the Hop3 workflow. Code, deploy, iterate. No infrastructure PhD required.

*For deeper configuration options, see [Designing hop3.toml](2026-02-hop3-toml-reference.md). Questions? Hit a snag? [Open an issue](https://github.com/abilian/hop3/issues) and we'll help you out.*
