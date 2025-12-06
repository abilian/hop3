# Demo 2: Docker Deployment

Deploys a Docker-based application with auto-generated docker-compose.yml.

## What It Demonstrates

- Building Docker images from a Dockerfile
- Auto-generated docker-compose.yml from EXPOSE directive
- Nginx reverse proxy to Docker containers
- Docker lifecycle management via Hop3 CLI

## Sample Application

```
hello-docker/
├── app.py           # Flask application
├── requirements.txt # Python dependencies
├── Dockerfile       # Container definition
└── hop3.toml        # Hop3 configuration
```

### Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8080"]
```

### hop3.toml

```toml
[build]
builder = "docker"
```

## How It Works

1. Hop3 detects `builder = "docker"` in hop3.toml
2. Runs `docker build` to create the image
3. Generates docker-compose.yml based on EXPOSE port
4. Starts container with `docker compose up`
5. Configures Nginx to proxy to the container

### Generated docker-compose.yml

```yaml
services:
  web:
    image: ${HOP3_IMAGE_TAG}
    ports:
      - "127.0.0.1:${PORT:-8080}:8080"
    environment:
      - PORT=8080
    restart: unless-stopped
```

For multi-container apps, provide your own docker-compose.yml.

## Comparison with Demo 1

| Aspect | Demo 1 (uWSGI) | Demo 2 (Docker) |
|--------|----------------|-----------------|
| Runtime | Python virtualenv + uWSGI | Docker container |
| Build | pip install | docker build |
| Isolation | Process-level | Container-level |
| Portability | Python-specific | Any language |

## Run This Demo

```bash
# From the repository root
python demos/demo.py <server_ip> demo2

# Keep app running after demo
python demos/demo.py <server_ip> demo2 --no-cleanup
```

See the [main README](../README.md) for all options.

## Docker Troubleshooting

### Permission Denied on docker.sock

```bash
# Add hop3 to docker group
usermod -aG docker hop3

# Restart to apply
systemctl restart hop3-server
```

### Container Logs

```bash
su - hop3
docker logs hello-docker-web-1
```
