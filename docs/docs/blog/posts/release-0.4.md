# Hop3 0.4 Released

*February 2026*

We're excited to announce the release of Hop3 0.4, a major architectural milestone that transforms Hop3 into a modern, production-ready platform.

## Highlights

### New Client-Server Architecture

Hop3 0.4 introduces a clean separation between the CLI client (`hop3-cli`) and the server (`hop3-server`). They communicate via JSON-RPC over SSH or HTTP/HTTPS, enabling:

- Remote server management from your local machine
- Secure authenticated access with JWT tokens
- Multiple deployment methods including `git push`

### Plugin-Based Service System

The new addon/service framework makes it easy to provision and manage backing services:

```bash
# Create a PostgreSQL database
hop3 addons:create postgres myapp-db

# Attach it to your application
hop3 addons:attach myapp myapp-db
```

Service credentials are now encrypted and persisted, surviving server restarts.

### Cross-Platform OS Support

Hop3 now runs on virtually any Linux distribution:

- **Debian family**: Debian, Ubuntu, and derivatives
- **Red Hat family**: RHEL, Rocky, Alma, Fedora, CentOS
- **Others**: Arch, BSD, and macOS (for development)

### Enhanced Security

- JWT authentication with bcrypt password hashing
- Role-based access control
- Encrypted credential storage using Fernet AEAD encryption
- Automatic SBOM generation for supply chain security
- Fixed critical authentication bypass vulnerability

## Breaking Changes

**Service Credentials**: The new encryption system requires setting `HOP3_SECRET_KEY` environment variable for production deployments.

**Proxy Configuration**: The `HOST_NAME` environment variable is now standardized across all proxy plugins (Nginx, Caddy, Traefik).

## What's Next

We're already working on Hop3 0.5, which will bring:

- Web-based management UI
- Enhanced backup and restore capabilities
- More language toolchains
- Improved monitoring and observability

## Get Started

```bash
# Install the CLI
curl -LsSf https://hop3.cloud/install-cli.py | python3 -

# Or upgrade an existing installation
hop3-install cli --upgrade
```

See the [Installation Guide](/get-started/installation/) for complete instructions.

## Thank You

Thanks to everyone who contributed to this release through code, testing, documentation, and feedback. Hop3 is built by and for the community.

For the complete list of changes, see the [Changelog](/reference/changelog/).
