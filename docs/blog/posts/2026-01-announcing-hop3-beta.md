---
date: 2026-01-09
template: blog_post.html
description: First public beta release of Hop3 0.4, an open-source PaaS for self-hosted deployments.
tags:
  - Announcement
  - Release
---

# Announcing Hop3 0.4 Beta: A Modern Open-Source PaaS

We're excited to announce the first public beta of Hop3, an open-source Platform as a Service designed for simplicity, security, and strategic autonomy.

## What is Hop3?

Hop3 is a PaaS that lets you deploy and manage web applications on your own server. Think Heroku, but self-hosted and without the complexity of Kubernetes or Docker Swarm.

```bash
# Install Hop3 on your server
curl -LsSf https://hop3.cloud/install-server.py | sudo python3 -

# Deploy an app
git push hop3 main
```

That's it. Your app is live with automatic SSL, reverse proxy configuration, and process management.

## Why We Built Hop3

Modern deployment platforms tend toward two extremes: managed services that lock you in (Heroku, Render, Railway) or container orchestrators that require dedicated operations teams (Kubernetes, Nomad).

We wanted something in between:

- **Simple**: One server, one command to deploy
- **Sovereign**: Your code runs on your infrastructure
- **Secure**: No containers required in production (though we support them)
- **Extensible**: Plugin architecture for customization

Hop3 builds on the foundation of [piku](https://github.com/piku/piku), adding a modern client-server architecture, multi-language toolchains, and a plugin system.

## What Works Today

### Multi-Language Support

Deploy applications in any of these languages:

| Language | Toolchain | Build System |
|----------|-----------|--------------|
| Python | pip, Poetry, uv | virtualenv |
| Node.js | npm, yarn, pnpm | node_modules |
| Ruby | Bundler | rbenv |
| Go | go modules | native binary |
| Rust | Cargo | native binary |
| PHP | Composer | Apache/nginx |
| Java | Maven, Gradle | JAR/WAR |
| Clojure | Leiningen | uberjar |

### Database Addons

Provision databases with a single command:

```bash
# Create a PostgreSQL database
hop3 addons create postgres myapp-db

# Attach it to your app (injects DATABASE_URL)
hop3 addons attach myapp myapp-db
```

Supported addons: PostgreSQL, MySQL, Redis.

### Automatic SSL

Hop3 integrates with Let's Encrypt for automatic certificate provisioning and renewal. Point your domain, deploy your app, and HTTPS just works.

### Reverse Proxy Options

Choose your reverse proxy:

- **Nginx** (default) - Battle-tested, excellent performance
- **Caddy** - Automatic HTTPS, simple configuration
- **Traefik** - Dynamic configuration, container-native

### Multi-Distribution Support

Hop3 runs on:

- Ubuntu 22.04, 24.04
- Debian 12, 13
- Fedora 41+
- Rocky Linux 9, AlmaLinux 9

## Architecture

Hop3 uses a client-server architecture:

```
┌─────────────┐         ┌─────────────────┐
│  hop3 CLI   │──SSH───▶│   hop3-server   │
│  (local)    │  tunnel │   (remote)      │
└─────────────┘         └─────────────────┘
```

The CLI (`hop3`) runs on your development machine. It communicates with `hop3-server` via JSON-RPC over SSH or HTTPS. This means:

- No agent to install on your laptop
- Secure by default (SSH or JWT auth)
- Works from anywhere

## Getting Started

### Install the Server

On a fresh Ubuntu/Debian server:

```bash
curl -LsSf https://hop3.cloud/install-server.py | sudo python3 -
```

### Install the CLI

On your development machine, install via pip or uv:

```bash
pip install hop3-cli
# or
uv tool install hop3-cli
```

### Deploy Your First App

```bash
# Add the Hop3 remote
git remote add hop3 hop3@your-server.com:myapp

# Deploy
git push hop3 main
```

Or use the CLI directly:

```bash
hop3 deploy myapp
```

## What's Coming

Hop3 is in active development. Here's what we're working on:

- **Web Dashboard**: Browser-based management UI
- **More Addons**: MongoDB, Elasticsearch, RabbitMQ
- **Backup/Restore**: Automated backups with point-in-time recovery
- **Monitoring**: Built-in metrics and alerting
- **Nix Integration**: Reproducible builds with Nix

## Get Involved

Hop3 is open source under the Apache 2.0 license.

- **GitHub**: [github.com/abilian/hop3](https://github.com/abilian/hop3)
- **Documentation**: [hop3.cloud](https://hop3.cloud)
- **Issues**: Report bugs and request features on GitHub

We'd love your feedback. Try deploying an app and let us know how it goes!

## Acknowledgments

Hop3 development is supported by [NGI Zero](https://nlnet.nl/NGI0/) through the European Commission's Next Generation Internet program. We're grateful for their support of open-source infrastructure.

---

*Ready to try Hop3? Check out our [first deployment tutorial](2026-02-deploying-first-app.md) or jump straight to the [Installation instructions](/get-started/server-setup/). To understand our motivation, read [Why We're Building Hop3](2026-01-why-hop3.md).*
