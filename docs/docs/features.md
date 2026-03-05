# Features

Hop3 is an open-source Platform as a Service (PaaS) for deploying and managing web applications on a single server.

## Core Features

### Multi-Language Support

Deploy applications in any popular programming language:

| Language | Frameworks | Status |
|----------|-----------|--------|
| Python | Flask, Django, FastAPI, Litestar | Stable |
| Node.js | Express, Fastify, Next.js, Nuxt | Stable |
| Ruby | Rails, Sinatra | Stable |
| Go | Gin, Fiber, standard library | Stable |
| Rust | Axum, Actix-web | Stable |
| PHP | Laravel, Symfony | Stable |
| Java | Spring Boot, Quarkus | Stable |
| Elixir | Phoenix | Stable |
| .NET | ASP.NET Core | Stable |

### Git-Based Deployment

Push to deploy with simple Git workflows:

```bash
# Deploy from local directory
hop3 deploy myapp

# Deploy from Git repository
hop3 deploy myapp --git https://github.com/user/repo
```

### Database Addons

Managed database services with automatic connection configuration:

- **PostgreSQL** - Full-featured relational database
- **MySQL/MariaDB** - Popular relational database
- **Redis** - In-memory data store and cache

```bash
hop3 addons:create postgres mydb
hop3 addons:attach mydb --app myapp
# DATABASE_URL automatically injected
```

### Automatic SSL/TLS

Free SSL certificates via Let's Encrypt with automatic renewal:

- Automatic provisioning when HOST_NAME is configured
- Automatic renewal before expiration
- Support for custom certificates

### Reverse Proxy

Automatic Nginx configuration for each application:

- HTTP/HTTPS routing
- WebSocket support
- Custom domain support
- Load balancing (multiple workers)

### Process Management

Robust process management via uWSGI:

- Procfile-based worker configuration
- Automatic restart on failure
- Graceful shutdown and reload
- Multiple worker processes

### Environment Configuration

Flexible configuration management:

```bash
hop3 config:set myapp KEY=value
hop3 config:show myapp
```

### CLI Interface

Full-featured command-line interface:

```bash
hop3 apps               # List applications
hop3 app:status myapp   # Application details
hop3 app:logs myapp     # View logs
hop3 app:restart myapp  # Restart application
```

### Web Dashboard

Browser-based management interface:

- Application overview and status
- Real-time log viewing
- System health monitoring
- User authentication

---

## Application Configuration

### hop3.toml

Declarative application configuration:

```toml
[app]
name = "myapp"

[build]
before-build = ["npm install"]
build = "npm run build"

[run]
web = "npm start"

[env]
NODE_ENV = "production"

[[provider]]
name = "postgres"
```

See the [Configuration Reference](reference/config.md) for full documentation.

---

## Infrastructure

### Supported Operating Systems

- Debian 12 (Bookworm) - Recommended
- Ubuntu 22.04 LTS, 24.04 LTS
- Rocky Linux 9
- NixOS (experimental)

### Single-Server Architecture

Hop3 is designed for single-server deployments:

- Simple installation and maintenance
- All components on one machine
- Ideal for small to medium workloads
- No Kubernetes or Docker required for production

### Plugin Architecture

Extensible via plugins:

- **Builders**: Local, Docker, Nix (planned)
- **Toolchains**: Language-specific build tools
- **Deployers**: uWSGI, Docker Compose, Static
- **Proxies**: Nginx, Caddy (planned), Traefik (planned)
- **Addons**: PostgreSQL, MySQL, Redis

---

## Security

### Authentication

- JWT-based API authentication
- Session-based web authentication
- API token generation for automation

### Application Isolation

- Separate directories per application
- Isolated virtual environments
- Dedicated database credentials
- Process isolation via uWSGI

### Network Security

- Automatic SSL/TLS encryption
- Firewall-friendly (ports 80/443)
- Database connections over localhost

---

## Operational Features

### Health Checks

```bash
hop3 system:check --verbose
```

Checks:
- Core services (hop3-server, nginx, uwsgi)
- Database addons
- Disk space
- SSL certificates

### Backup & Restore

```bash
hop3 backup:create mydb
hop3 backup:list
hop3 backup:restore mydb --backup <file>
```

### Logging

```bash
hop3 app:logs myapp --follow
hop3 system:logs
```

---

## Roadmap Features

The following features are planned for future releases:

| Feature | Status | Target |
|---------|--------|--------|
| Nix-based builds | In Development | Q2 2026 |
| Multi-server clustering | Planned | Q3 2026 |
| Web terminal | Planned | Q2 2026 |
| LDAP/SSO integration | Planned | Q3 2026 |
| Advanced monitoring | Planned | Q2 2026 |
| WAF integration | In Development | Q1 2026 |

---

## Comparison

### vs Heroku

- **Self-hosted**: Full control over infrastructure
- **No vendor lock-in**: Open source, run anywhere
- **Cost**: Free software, pay only for hosting
- **Similar DX**: Git push deployment, addons, environment config

### vs Dokku

- **Modern stack**: Python-based, Litestar framework
- **Plugin system**: Pluggy-based extensibility
- **Web UI**: Built-in dashboard
- **Database**: SQLAlchemy ORM for metadata

### vs Kubernetes

- **Simplicity**: Single server, no orchestration complexity
- **Target**: Small to medium deployments
- **Learning curve**: Minutes to deploy, not days
- **Resource efficient**: No cluster overhead
