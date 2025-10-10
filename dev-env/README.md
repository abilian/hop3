# Hop3 Development Environment

Complete, isolated Docker-based development environment for Hop3 with full uWSGI, nginx, and PostgreSQL support.

## Features

- Production-like environment (uWSGI, nginx, PostgreSQL, SSH)
- No root access required on host machine
- Fully isolated from host system
- Persistent data volumes
- Automatic nginx reload on deployment
- Self-signed SSL certificates for development

## Prerequisites

- Docker Desktop installed and running

## Quick Start

### 1. Initial Setup (5-10 minutes)

```bash
cd dev-env
./setup.sh      # Build Docker image
./start.sh      # Start container
./setup-cli.sh  # Configure hop CLI on host
```

### 2. Deploy an App

**Recommended**: Use hop CLI from your host machine (just like production):

```bash
# Deploy any app
hop deploy myapp /path/to/your/app

# Check status
hop app:status myapp
hop apps

# View logs
hop app:logs myapp
```

Your app will be accessible at **http://localhost:8080/**

### 3. Stop the Environment

```bash
cd dev-env
./stop.sh
```

## Complete Example

```bash
# 1. Create a simple Flask app
mkdir -p /tmp/hello && cd /tmp/hello

cat > app.py << 'EOF'
from flask import Flask
app = Flask(__name__)

@app.route('/')
def hello():
    return 'Hello from Hop3!'
EOF

cat > requirements.txt << 'EOF'
flask
gunicorn
EOF

cat > Procfile << 'EOF'
web: gunicorn -b 0.0.0.0:$PORT app:app
EOF

# 2. Start dev environment
cd /path/to/hop3/dev-env
./start.sh

# 3. Deploy from host machine
hop deploy hello /tmp/hello

# 4. Test it
curl http://localhost:8080/
# Returns: Hello from Hop3!

hop apps
# Shows: hello (RUNNING, 1 worker)
```

## Available Scripts

| Script | Purpose |
|--------|---------|
| `./setup.sh` | One-time setup: build Docker image |
| `./start.sh` | Start the container and all services |
| `./stop.sh` | Stop the container |
| `./rebuild.sh` | Rebuild after hop3-server code changes |
| `./status.sh` | Check service status (nginx, postgres, etc.) |
| `./shell.sh` | Open bash shell inside container |
| `./logs.sh [service]` | View logs (nginx, uwsgi, postgres, hop3-server) |
| `./test.sh` | Test all services are accessible |
| `./run.sh <cmd>` | Run arbitrary commands inside container |
| `./setup-cli.sh` | Install and configure hop CLI on host |

## Exposed Services

| Service | Host Access | Description |
|---------|-------------|-------------|
| hop3-server API | http://localhost:8000 | JSON-RPC API |
| HTTP (nginx) | http://localhost:8080 | Apps accessible here |
| HTTPS (nginx) | https://localhost:8443 | SSL with self-signed certs |
| SSH | localhost:2222 | User: hop3, Pass: hop3 |
| PostgreSQL | localhost:5432 | For service testing |

## Common Workflows

### Deploy and Test

```bash
# Start environment
./start.sh

# Deploy your app from host
hop deploy myapp ~/projects/my-flask-app

# Check it's running
hop app:status myapp

# Access via HTTP
curl http://localhost:8080/

# View logs
hop app:logs myapp
```

### Update Code and Redeploy

```bash
# 1. Make changes to your app locally
# 2. Redeploy
hop deploy myapp ~/projects/my-flask-app

# App rebuilds and restarts automatically
```

### After hop3-server Code Changes

If you modify hop3-server source code:

```bash
cd dev-env
./rebuild.sh    # Rebuilds Docker image (includes hop3-server)
./stop.sh && ./start.sh
```

### Multi-App Deployment

Each app needs a unique hostname. Set via `/etc/hosts` or environment variables:

```bash
# Deploy multiple apps
hop deploy app1 /path/to/app1
hop deploy app2 /path/to/app2

# Configure hostnames (add to /etc/hosts)
echo "127.0.0.1 app1.local app2.local" | sudo tee -a /etc/hosts

# Access specific apps
curl -H "Host: app1.local" http://localhost:8080/
curl -H "Host: app2.local" http://localhost:8080/
```

### Testing PostgreSQL Services

```bash
# Create database service
hop services:create postgres mydb

# Attach to app
hop services:attach mydb myapp

# DATABASE_URL is now set in app environment
hop config myapp
```

### Debugging

```bash
# View all logs
./logs.sh

# View specific service logs
./logs.sh nginx
./logs.sh uwsgi-emperor
./logs.sh postgres
./logs.sh hop3-server

# Open shell for investigation
./shell.sh

# Inside shell:
ls -la ~/.hop3/apps/
cat ~/.hop3/apps/myapp/log/web.1.log
supervisorctl status
```

### SSH Access

```bash
ssh -p 2222 hop3@localhost
# Password: hop3
```

## Data Persistence

Docker volumes persist data across container restarts:

- `hop3-apps`: App deployments and code
- `hop3-data`: Application data directories
- `hop3-postgres`: PostgreSQL databases

To wipe all data:

```bash
docker compose down -v  # ⚠️ Deletes everything!
./setup.sh              # Start fresh
```

## Directory Structure

Inside the container at `/home/hop3/.hop3/`:

```
apps/           # Deployed applications
├── myapp/
│   ├── src/    # Source code
│   ├── venv/   # Python virtualenv
│   ├── log/    # Application logs
│   └── data/   # Persistent data

cache/          # Build cache
certificates/   # SSL certificates
nginx/          # Nginx virtual host configs
uwsgi/          # uWSGI emperor config
uwsgi-available/  # Available app configs
uwsgi-enabled/    # Symlinks to enabled configs
```

## Troubleshooting

### Container won't start

```bash
# Check Docker is running
docker ps

# Check logs
docker compose logs

# Rebuild from scratch
docker compose down -v
./setup.sh
```

### App won't deploy

```bash
# Check app has required files
ls -la /path/to/app/
# Must have: Procfile or hop3.toml
# Plus: requirements.txt (Python) or package.json (Node)

# Check build logs
hop app:logs myapp

# Check inside container
./shell.sh
ls -la ~/.hop3/apps/myapp/
```

### Can't access app via HTTP

```bash
# Check services are running
./status.sh

# Check app is running
hop app:status myapp

# Check nginx config was created
./shell.sh
ls -la ~/.hop3/nginx/myapp.conf

# Check nginx logs
./logs.sh nginx
```

### Port already in use

Edit `docker-compose.yml` to change port mappings:

```yaml
ports:
  - "2223:22"     # Change 2222 to 2223
  - "8081:80"     # Change 8080 to 8081
  # etc.
```

## Architecture

Services managed by supervisord:
- `nginx`: Web server (ports 80/443)
- `uwsgi-emperor`: uWSGI process manager
- `postgresql`: Database server
- `sshd`: SSH server
- `hop3-server`: JSON-RPC API server (port 8000)

Deployment flow:
1. hop CLI sends app files to hop3-server (port 8000)
2. hop3-server extracts files to `~/.hop3/apps/myapp/src/`
3. Builds virtualenv, installs dependencies
4. Creates uWSGI config in `uwsgi-available/`
5. Symlinks to `uwsgi-enabled/`
6. Creates nginx config in `nginx/`
7. Reloads nginx (automatic!)
8. uWSGI emperor starts app workers
9. App accessible at http://localhost:8080/

## What's Different from Production?

This environment is very close to production, with:

- ✅ All services in one container (vs separate containers/VMs)
- ✅ Self-signed SSL certificates (no Let's Encrypt)
- ✅ Default passwords (change in production!)
- ✅ More verbose logging
- ✅ Development mode settings

## Further Reading

- [QUICKSTART.md](QUICKSTART.md) - Quick reference guide
- Main Hop3 docs - See `docs/` directory in repository

---

**Enjoy your full-featured Hop3 development environment!** 🚀

For issues or questions, check the logs with `./logs.sh` or open a shell with `./shell.sh`.
