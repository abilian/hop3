---
icon: lucide/cloud
---

# Hop3 - Open Source Platform as a Service

<div style="text-align: center; margin: 2rem 0;">
<img src="https://abilian.com/static/images/ext/hop3-logo.png" style="width: 400px; height: auto;" alt="Hop3 Logo"/>
</div>

**Hop3** is an open-source Platform as a Service (PaaS) that enables you to deploy and manage your applications seamlessly. It is designed to be **simple**, **secure**, and **sovereignty-focused**.

!!! warning "Development Status"
    Hop3 is actively developed and still undergoing active architecture and API changes. Version 0.4.x is considered alpha quality. For bleeding-edge features, consider the `devel` branch on git.

## Quick Links

<div class="grid cards" markdown>

-   :material-rocket-launch: **[Quick Start](get-started/quickstart.md)**

    Deploy your first application in minutes

-   :material-book-open-variant: **[User Guide](guides/user-guide.md)**

    Complete guide to using Hop3

-   :material-console: **[CLI Reference](reference/cli.md)**

    Full command reference

-   :material-cog: **[Configuration](reference/config.md)**

    hop3.toml configuration reference

</div>

## Why Hop3?

### Sovereignty First

Maintain complete control over your data and infrastructure. Deploy on your own servers without relying on centralized cloud services.

### Simple by Design

No Docker, no Kubernetes complexity. Deploy applications with `git push` simplicity using familiar toolchains (Python, Node.js, Go, Ruby, Rust, and more).

### Secure by Default

- Automatic HTTPS with Let's Encrypt
- Built-in security best practices
- GDPR and CRA compliance ready
- Regular security audits

### Sustainable Computing

Lightweight architecture optimized for efficiency. Run multiple applications on modest hardware with minimal resource overhead.

## Features

=== "Application Deployment"

    - **Git-based deploys**: Push to deploy your applications
    - **Multiple languages**: Python, Node.js, Go, Ruby, Rust, PHP, Java, Elixir
    - **Process management**: Automatic process lifecycle management
    - **Zero-downtime deploys**: Rolling updates without interruption

=== "Service Management"

    - **Database addons**: PostgreSQL, MySQL, Redis
    - **Automatic backups**: Scheduled backup and restore
    - **SSL certificates**: Let's Encrypt integration
    - **Multiple frontends**: Nginx, Caddy, or Traefik

=== "Administration"

    - **Web dashboard**: Real-time monitoring and management
    - **CLI tools**: Full command-line interface
    - **API access**: JSON-RPC API for automation
    - **Multi-user**: Team management with access control

## Getting Started

1. **Install the CLI** on your local machine:

    ```bash
    curl -LsSf https://hop3.cloud/install-cli.py | python3 -
    ```

2. **Install the server** on your deployment target:

    ```bash
    curl -LsSf https://hop3.cloud/install-server.py | sudo python3 -
    ```

3. **Deploy your first app**:

    ```bash
    hop3 deploy myapp
    ```

See the [Installation Guide](get-started/server-setup.md) for detailed instructions.

## Supported Platforms

| Operating System | Status |
|------------------|--------|
| Ubuntu 24.04+ | :material-check: Supported |
| Debian 12+ | :material-check: Supported |
| Rocky Linux 9+ | :material-check: Supported |
| Arch Linux | :material-check: Supported |
| NixOS | :material-flask: Experimental |
| FreeBSD | :material-flask: Experimental |

## Community

- **GitHub**: [github.com/abilian/hop3](https://github.com/abilian/hop3)
- **Matrix Chat**: [#hop3:matrix.org](https://matrix.to/#/#hop3:matrix.org)
- **SourceHut**: [git.sr.ht/~sfermigier/hop3](https://git.sr.ht/~sfermigier/hop3)

## Funding

Hop3 is partly funded through the [NGI0 Commons Fund](https://nlnet.nl/commonsfund), established by NLnet with support from the European Commission's Next Generation Internet programme.

---

*Copyright © 2021-2026 [Abilian SAS](https://www.abilian.com/). Licensed under AGPL-3.0.*
