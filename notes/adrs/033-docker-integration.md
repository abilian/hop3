# ADR 033: Docker Integration Strategy

**Status**: Accepted
**Date**: 2025-12-04
**Related ADRs**: ADR 030 (Two-Level Build Architecture), ADR 032 (Deployment Strategies)

## Context

Hop3 currently supports native deployment using uWSGI and nginx. However, some applications require containerization, either because:

1. They have complex dependencies that are difficult to install natively
2. They need process isolation beyond what uWSGI provides
3. They are already packaged as Docker images
4. They require multi-container setups (app + database + cache)

The Docker plugin (`hop3/plugins/docker/`) provides an alternative build and deployment path for containerized applications.

## Decision

### Architecture

Docker integration follows the two-level build architecture (ADR 030):

```
Level 1 (Builder)          Level 2 (Toolchain)
┌─────────────────┐        ┌─────────────────────┐
│ LocalBuilder    │───────▶│ PythonToolchain     │
│                 │        │ NodeToolchain       │
│                 │        │ ...                 │
└─────────────────┘        └─────────────────────┘
┌─────────────────┐
│ DockerBuilder   │ (standalone - no toolchains)
└─────────────────┘
```

**DockerBuilder** is a Level 1 Builder that:
- Does NOT use Level 2 toolchains
- Builds directly from a Dockerfile
- Produces `docker-image` artifacts

### Build Flow

```
Source Code                DockerBuilder              DockerComposeDeployer
┌───────────────┐           ┌─────────────┐           ┌────────────────┐
│ app/          │           │             │           │                │
│ ├─ src/       │──────────▶│ docker      │──────────▶│ docker compose │
│ ├─ Dockerfile │           │ build       │           │ up -d          │
│ └─ compose.yml│           │             │           │                │
└───────────────┘           └─────────────┘           └────────────────┘
                                │                            │
                                ▼                            ▼
                         BuildArtifact               DeploymentInfo
                         kind="docker-image"         protocol="http"
                         location="hop3/app:latest"  port=8080
```

### Detection Rules

| Builder | Accepts When |
|---------|--------------|
| LocalBuilder | Any language toolchain accepts (requirements.txt, package.json, etc.) |
| DockerBuilder | `Dockerfile` exists in source directory |

| Deployer | Accepts When |
|----------|--------------|
| UWSGIDeployer | Artifact kind is `virtualenv`, `node`, `ruby`, etc. |
| StaticDeployer | Artifact kind is `static` |
| DockerComposeDeployer | Artifact kind is `docker-image` AND `docker-compose.yml` exists |

### Docker Compose File Requirements

Applications using Docker deployment must provide a `docker-compose.yml` (or `compose.yml`) that references the built image via environment variable:

```yaml
# docker-compose.yml
version: '3.8'

services:
  web:
    image: ${HOP3_IMAGE_TAG}
    ports:
      - "${HOP3_APP_PORT:-8080}:8080"
    environment:
      - DATABASE_URL=${DATABASE_URL:-}
```

Hop3 provides these environment variables to the compose file:
- `HOP3_IMAGE_TAG`: The Docker image tag (e.g., `hop3/myapp:latest`)
- `HOP3_APP_NAME`: The application name
- `HOP3_APP_PORT`: The exposed port from Dockerfile (if detected)

### Proxy Integration

**Current State**: Docker-deployed apps do NOT integrate with Hop3's proxy system (nginx/caddy/traefik).

**Future Work**: To enable proxy integration:

1. **Option A: Traefik labels** (Recommended)
   - Add Traefik labels to docker-compose services
   - Traefik auto-discovers containers and routes traffic
   - Requires Traefik to be the configured proxy

2. **Option B: Manual nginx config**
   - DockerComposeDeployer generates nginx upstream config
   - Points to container's published port
   - Similar to current UWSGIDeployer approach

3. **Option C: Docker network bridge**
   - Create a shared Docker network for Hop3 apps
   - Nginx runs in a container on the same network
   - Route by container name, not port

### Lifecycle Management

DockerComposeDeployer implements the full Deployer protocol:

| Method | Docker Compose Command |
|--------|----------------------|
| `deploy()` | `docker compose up -d --remove-orphans` |
| `start()` | `docker compose up -d` |
| `stop()` | `docker compose stop` |
| `restart()` | `docker compose restart` |
| `destroy()` | `docker compose down --volumes` |
| `scale()` | `docker compose up -d --scale web=N` |
| `check_status()` | `docker compose ps` |

### Port Discovery

Ports are discovered in this order:

1. `EXPOSE` directive in Dockerfile (parsed during build)
2. `docker compose port` command (runtime discovery)
3. Fallback to 8080

## Implementation Status

| Component | Status | Tests |
|-----------|--------|-------|
| DockerBuilder | ✅ Implemented | ✅ 14 tests |
| DockerComposeDeployer | ✅ Implemented | ✅ 16 tests |
| DockerPlugin (registration) | ✅ Implemented | - |
| Proxy integration | ❌ Not implemented | - |
| Multi-stage builds | ❌ Not implemented | - |
| Build args support | ❌ Not implemented | - |

## Future Enhancements

### Phase 1: Proxy Integration

Add Traefik labels to docker-compose for automatic routing:

```yaml
services:
  web:
    image: ${HOP3_IMAGE_TAG}
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.${HOP3_APP_NAME}.rule=Host(`${HOST_NAME}`)"
```

### Phase 2: Build Improvements

1. **Build arguments**: Pass environment variables as build args
2. **Multi-stage builds**: Support for complex Dockerfiles
3. **Buildx support**: Enable BuildKit features
4. **Image caching**: Reuse layers across deployments

### Phase 3: Advanced Orchestration

1. **Health checks**: Monitor container health
2. **Rolling updates**: Zero-downtime deployments
3. **Resource limits**: CPU/memory constraints
4. **Secrets management**: Integrate with Docker secrets

## Consequences

### Positive

- Supports applications that require containerization
- Consistent lifecycle management (same API as uWSGI deployer)
- Multi-container applications supported via compose
- Tested with 30 unit tests

### Negative

- Requires Docker to be installed on the server
- No automatic proxy integration (must be configured manually)
- Port discovery is heuristic-based
- Scaling requires compose file to support it

### Neutral

- Docker apps are isolated from native apps
- Different deployment model than uWSGI (containers vs processes)

## Example Usage

### Minimal Docker App

```
myapp/
├── Dockerfile
├── docker-compose.yml
├── app.py
└── requirements.txt
```

**Dockerfile:**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["python", "app.py"]
```

**docker-compose.yml:**
```yaml
version: '3.8'
services:
  web:
    image: ${HOP3_IMAGE_TAG}
    ports:
      - "8080:8080"
```

**Deploy:**
```bash
hop apps:create myapp
git push hop3 main
```

## References

- ADR 030: Two-Level Build Architecture
- ADR 032: Deployment Strategies & Artifact Lifecycle
- Docker Compose specification: https://docs.docker.com/compose/compose-file/
