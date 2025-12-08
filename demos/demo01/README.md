# Demo 1: uWSGI Deployment

Deploys a Python/Flask application using uWSGI as the application server.

## What It Demonstrates

- Deploying a Python app with `requirements.txt`
- uWSGI as the WSGI server
- Nginx reverse proxy configuration
- Environment variable management
- Application lifecycle (deploy, restart, destroy)

## Sample Application

```
hello-hop3/
├── app.py           # Flask application
├── requirements.txt # Python dependencies
└── hop3.toml        # Hop3 configuration
```

### app.py

```python
from flask import Flask
app = Flask(__name__)

@app.route("/")
def hello():
    return "Hello, Hop3!"
```

### hop3.toml

```toml
[web]
# uWSGI is the default, no explicit builder needed
```

## Run This Demo

```bash
# From the repository root
python demos/demo.py <server_ip> demo1

# Keep app running after demo
python demos/demo.py <server_ip> demo1 --no-cleanup
```

See the [main README](../README.md) for all options.
