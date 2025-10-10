# Hop3 Dev Environment - Quick Start

## First Time Setup (5-10 minutes)

```bash
cd dev-env

# 1. Build and start the container
./setup.sh
./start.sh

# 2. Install hop CLI locally and configure it
./setup-cli.sh
```

## Daily Workflow

Use the hop CLI from your host machine, just like production:

```bash
# 1. Start the dev container (if not already running)
cd dev-env
./start.sh

# 2. Deploy from your host machine
hop deploy myapp /path/to/app

# 3. Check status
hop app:status myapp

# 4. View logs
hop app:logs myapp

# 5. Access via browser
open http://localhost:8080/myapp

# 6. When done
cd dev-env
./stop.sh
```

## Alternative: Manual Workflow (for debugging)

```bash
# Deploy by copying files manually
./deploy.sh myapp /path/to/app

# Run commands inside container
./run.sh hop app:status myapp
```

## Most Used Commands

```bash
./start.sh              # Start everything
./stop.sh               # Stop everything
./status.sh             # Check what's running
./shell.sh              # Open a shell inside
./logs.sh               # View all logs
./deploy.sh NAME DIR    # Deploy an app
./run.sh hop <command>  # Run hop commands
```

## Example: Deploy a Flask App

```bash
# Create test app
mkdir -p /tmp/hello
cd /tmp/hello

cat > app.py << 'EOF'
from flask import Flask
app = Flask(__name__)

@app.route('/')
def hello():
    return 'Hello World!'
EOF

cat > requirements.txt << 'EOF'
flask
EOF

cat > Procfile << 'EOF'
web: flask run --host=0.0.0.0 --port=$PORT
EOF

# Deploy it
cd /path/to/hop3/dev-env
./deploy.sh hello /tmp/hello

# Test it
./run.sh hop app:status hello
curl http://localhost:8080/hello
```

## Troubleshooting

```bash
./status.sh              # What's running?
./logs.sh                # What went wrong?
./shell.sh               # Debug inside container
docker compose down -v   # Nuclear option: delete everything
./setup.sh               # Start fresh
```

## Full Documentation

See [README.md](README.md) for complete details.
