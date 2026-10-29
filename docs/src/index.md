---
icon: lucide/cloud
---

# Hop3 - Open Source Platform as a Service

<div class="hop3-hero">
<img src="img/hop3-lockup.svg" class="only-light" alt="Hop3 — The cloud is yours"/>
<img src="img/hop3-lockup-dark.svg" class="only-dark" alt="Hop3 — The cloud is yours"/>
</div>

**Hop3** is an open-source Platform as a Service (PaaS) for deploying and managing your applications. It is designed to be **simple**, **secure**, and **sovereignty-focused**.

!!! warning "Development Status"
    Hop3 is beta-quality software: its architecture and APIs can still change between releases.

## In six slides

<div class="deck" data-pdf="pdf/hop3.pdf"><a href="pdf/hop3.pdf">Hop3, in six slides (PDF)</a></div>

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

Deploy applications with `git push` simplicity, using familiar toolchains (Python, Node.js, Go, Ruby, Rust, and more). Kubernetes is not involved. Docker is optional: apps build natively, with Nix or with Docker.

### Secure by Default

- Automatic HTTPS with Let's Encrypt
- Privilege separation: the server runs unprivileged, and root-level actions go through a narrow, audited daemon
- A role for each account, checked on every command and dashboard page
- A web application firewall ([LeWAF](reference/config.md#waf-web-application-firewall-layer-7), the OWASP Core Rule Set) in front of any app that declares one
- Addon credentials encrypted in the server's database

### Sustainable Computing

Hop3 itself needs few resources, so several applications run side by side on modest hardware.

## Features

=== "Application Deployment"

    - **App catalog**: Install Nextcloud, Forgejo, WordPress and other ready-made apps from the dashboard or with `hop3 catalog install` ([guide](guides/app-catalog.md))
    - **Git-based deploys**: Push to deploy your applications
    - **Multiple languages**: Python, Node.js, Go, Ruby, Rust, PHP, Java, Elixir, Clojure, .NET, plus static sites
    - **Multiple builders**: Native toolchains, Nix, or Docker
    - **Process management**: Automatic process lifecycle management

=== "Service Management"

    - **Service addons**: PostgreSQL, MySQL, Redis, S3/MinIO object storage, email/SMTP
    - **Backup and restore**: Snapshot and restore app data and addons
    - **SSL certificates**: Let's Encrypt integration
    - **Reverse proxy**: Nginx, Caddy or Traefik. Traefik serves no static files or PHP. The web application firewall and the sign-in gate need nginx

=== "Administration"

    - **Web dashboard**: Monitor and manage your apps from the browser
    - **CLI tools**: Full command-line interface
    - **API access**: JSON-RPC API for automation
    - **Multi-user**: Named accounts, each with a role: `admin`, `deployer`, `viewer` or `member`
    - **Sign-in gate**: [`[access]`](reference/config.md#access-sign-in-gate) puts an app behind a Hop3 sign-in

## Getting Started

1. **Install the CLI** on your local machine:

    ```bash
    uv tool install hop3
    ```

    Without [uv](https://docs.astral.sh/uv/): `curl -LsSf https://hop3.cloud/install-cli.py | python3 -`.

2. **Install the server** on your deployment target:

    ```bash
    curl -LsSf https://hop3.cloud/install-server.py | sudo python3 -
    ```

3. **Sign in to your server** over SSH, from your own machine:

    ```bash
    hop3 login root@hop3.example.com
    ```

4. **Deploy your first app**, from its source directory. The first time, bind the checkout to the server you signed in to:

    ```bash
    cd myapp
    hop3 context use default
    hop3 deploy --app myapp
    ```

See the [Installation Guide](get-started/server-setup.md) for detailed instructions.

## Supported Platforms

| Operating System | Status | Tested in CI |
|------------------|--------|--------------|
| Ubuntu 24.04 / 26.04 LTS | :material-check: Supported | yes |
| Rocky Linux 9+ | :material-check: Supported | yes |
| NixOS | :material-check: Supported | yes |
| Debian 12+ | :material-check: Supported | via Ubuntu (same family) |
| Arch Linux | :material-flask: Experimental | no |
| FreeBSD | :material-flask: Experimental | no |
| macOS | :material-flask: Experimental | no |

## Community

- **GitHub**: [github.com/abilian/hop3](https://github.com/abilian/hop3)
- **Matrix Chat**: [#hop3:matrix.org](https://matrix.to/#/#hop3:matrix.org)
- **SourceHut**: [git.sr.ht/~sfermigier/hop3](https://git.sr.ht/~sfermigier/hop3)

## Funding

Hop3 was partly funded through the [NGI0 Commons Fund](https://nlnet.nl/commonsfund), established by NLnet with support from the European Commission's Next Generation Internet programme.

---

*Copyright © 2021-2026 [Abilian SAS](https://www.abilian.com/).*
