# Hop3 Installers

Single-file Python installers for the Hop3 CLI and Server components. These installers use only the Python standard library for maximum portability.

## Quick Start

### CLI Installation (end users)

```bash
# Install latest from PyPI
curl -LsSf https://hop3.cloud/install-cli.py | python3 -

# Or download and run with options
curl -LsSf https://hop3.cloud/install-cli.py -o install-cli.py
python3 install-cli.py --help
```

### Server Installation (server administrators)

```bash
# Install latest from PyPI
curl -LsSf https://hop3.cloud/install-server.py | sudo python3 -

# Or download and run with options
curl -LsSf https://hop3.cloud/install-server.py -o install-server.py
sudo python3 install-server.py --help
```

## Requirements

- **Python 3.10+** (checked at runtime)
- **Server installer**: Must be run as root
- **Git**: Required only when using `--git` flag

## CLI Installer (`install-cli.py`)

Installs the `hop3` command-line tool for deploying and managing applications on a Hop3 server.

### Installation Steps

1. Check system requirements (Python version, venv module)
2. Create virtual environment at `~/.hop3-cli/venv`
3. Install `hop3-cli` package
4. Create command symlinks (`hop3`, `hop`) in `~/.local/bin`
5. Update shell PATH configuration

### Command-Line Options

| Option | Environment Variable | Description |
|--------|---------------------|-------------|
| `--version VERSION` | `HOP3_VERSION` | Install specific version (e.g., `0.4.0`) |
| `--git` | `HOP3_GIT=1` | Install from git repository |
| `--branch BRANCH` | `HOP3_BRANCH` | Git branch (default: `main`) |
| `--local-path PATH` | `HOP3_LOCAL_PACKAGE` | Install from local directory |
| `--bin-dir PATH` | `HOP3_BIN_DIR` | Symlink directory (default: `~/.local/bin`) |
| `--force` | `HOP3_FORCE=1` | Force reinstall |
| `--no-modify-path` | `HOP3_NO_MODIFY_PATH=1` | Don't modify shell config |
| `--verbose` | `HOP3_VERBOSE=1` | Show verbose output |

### Examples

```bash
# Install latest from PyPI
python3 install-cli.py

# Install specific version
python3 install-cli.py --version 0.4.0

# Install from git (main branch)
python3 install-cli.py --git

# Install from git (specific branch)
python3 install-cli.py --git --branch develop

# Install from local directory (for development)
python3 install-cli.py --local-path /path/to/hop3/packages/hop3-cli

# Force reinstall
python3 install-cli.py --force

# Install without modifying shell config
python3 install-cli.py --no-modify-path
```

### Installation Locations

| Item | Path |
|------|------|
| Virtual environment | `~/.hop3-cli/venv` |
| Commands (`hop3`, `hop`) | `~/.local/bin/` |

### Uninstalling

```bash
rm -rf ~/.hop3-cli
rm -f ~/.local/bin/hop3 ~/.local/bin/hop
```

## Server Installer (`install-server.py`)

Installs the Hop3 server for hosting applications. Must be run as root.

### Installation Steps

1. Install system dependencies (via apt/dnf)
2. Create `hop3` user and group
3. Create virtual environment at `/home/hop3/venv`
4. Install `hop3-server` package
5. Run initial Hop3 setup
6. Configure SSH keys (if root keys exist)
7. Set up systemd services
8. Generate SSL certificate (self-signed by default)
9. Configure nginx as reverse proxy (and install `hop3-rootd`, the privileged-operations daemon used for nginx reloads)
10. Configure PostgreSQL
11. Configure MySQL (when requested via `--with mysql`)

After these steps the installer writes the server config, installs acme.sh, and verifies the installation.

### Command-Line Options

| Option | Environment Variable | Description |
|--------|---------------------|-------------|
| `--version VERSION` | `HOP3_VERSION` | Install specific version |
| `--git` | `HOP3_GIT=1` | Install from git repository |
| `--branch BRANCH` | `HOP3_BRANCH` | Git branch (default: `main`) |
| `--local-path PATH` | `HOP3_LOCAL_PACKAGE` | Install from local directory |
| `--pre` | | Allow pre-release versions when installing from PyPI |
| `--with FEATURES` | | Comma-separated optional features: `docker`, `mysql`, `redis`, `s3`, `nix`, `all` |
| `--domain DOMAIN` | `HOP3_DOMAIN` | Domain for Let's Encrypt certificate |
| `--acme-email EMAIL` | | Email address for Let's Encrypt registration (required for ACME) |
| `--force` | `HOP3_FORCE=1` | Force reinstall |
| `--skip-deps` | `HOP3_SKIP_DEPS=1` | Skip system dependency installation |
| `--skip-nginx` | `HOP3_SKIP_NGINX=1` | Skip nginx setup |
| `--skip-postgres` | `HOP3_SKIP_POSTGRES=1` | Skip PostgreSQL setup |
| `--skip-acme` | `HOP3_SKIP_ACME=1` | Skip ACME/Let's Encrypt setup |
| `--skip-package-install` | | Skip the `hop3-server` package install (when installed separately) |
| `--verbose` | `HOP3_VERBOSE=1` | Show verbose output |

PostgreSQL is always set up (unless `--skip-postgres`). The other backing services — MySQL, Redis, S3/MinIO object storage — and the optional Docker and Nix runtimes are enabled with `--with`, for example `--with redis,s3` or `--with all`.

### Examples

```bash
# Install with self-signed certificate (default)
sudo python3 install-server.py

# Install with Let's Encrypt certificate for a domain
sudo python3 install-server.py --domain hop3.example.com --acme-email you@example.com

# Install with optional backing services and runtimes
sudo python3 install-server.py --with redis,s3
sudo python3 install-server.py --with all

# Install from git (specific branch)
sudo python3 install-server.py --git --branch develop

# Install from local directory (for development)
sudo python3 install-server.py --local-path /path/to/hop3/packages/hop3-server

# Skip optional components
sudo python3 install-server.py --skip-postgres --skip-acme

# Using environment variables
HOP3_GIT=1 HOP3_BRANCH=develop sudo -E python3 install-server.py
```

### SSL Certificates

By default, the installer generates a **self-signed SSL certificate** for immediate HTTPS support. This is suitable for:
- Development and testing
- Internal/private servers
- Initial setup before configuring a domain

To use a **Let's Encrypt certificate**, provide a domain name and a registration email:

```bash
sudo python3 install-server.py --domain hop3.example.com --acme-email you@example.com
```

Requirements for Let's Encrypt:
- The domain must point to this server's IP address
- Ports 80 and 443 must be accessible from the internet
- The server must be reachable at the specified domain

Providing `--acme-email` writes `ACME_ENGINE=certbot` to `/etc/default/hop3`; without it the server stays on `ACME_ENGINE=self-signed`. Certificate renewal is then handled by the configured ACME engine.

**Note:** The installer configures nginx as the reverse proxy. Support for alternative proxies (Caddy, Traefik) is planned for future versions.

### Supported Distributions

| Distribution | Package Manager |
|--------------|-----------------|
| Ubuntu | apt |
| Debian | apt |
| Linux Mint | apt |
| Pop!_OS | apt |
| Fedora | dnf |
| RHEL/CentOS | dnf |
| Rocky Linux | dnf |
| AlmaLinux | dnf |

### System Dependencies

**Debian/Ubuntu packages:**
- bc, git, sudo, cron, build-essential
- nginx, postgresql, postgresql-contrib
- python3-dev, python3-pip, python3-venv
- curl, wget, rsync, socat
- Various development libraries

**Fedora/RHEL packages:**
- bc, git, sudo, cronie, gcc, gcc-c++, make
- nginx, postgresql-server, postgresql-contrib
- python3-devel, python3-pip
- curl, wget, rsync, socat
- Various development libraries

### Installation Locations

| Item | Path |
|------|------|
| User home | `/home/hop3` |
| Virtual environment | `/home/hop3/venv` |
| Commands | `/home/hop3/venv/bin/hop3-server` |
| Systemd services | `/etc/systemd/system/hop3-server.service` |
| uWSGI service | `/etc/systemd/system/uwsgi-hop3.service` |
| SSL certificate | `/etc/hop3/ssl/hop3.crt` |
| SSL private key | `/etc/hop3/ssl/hop3.key` |
| Nginx config (Debian) | `/etc/nginx/sites-available/hop3` |
| Nginx config (Fedora) | `/etc/nginx/conf.d/hop3.conf` |

### Systemd Services

Three services are configured:

- **hop3-server**: Main Hop3 server daemon (API server on port 8000)
- **uwsgi-hop3**: uWSGI emperor for application workers
- **nginx**: Reverse proxy for HTTPS termination

```bash
# Check status
sudo systemctl status hop3-server
sudo systemctl status uwsgi-hop3
sudo systemctl status nginx

# View logs
sudo journalctl -u hop3-server -f
```

For an application-level health report (server identity, addons, certificate status), use the CLI once it is installed:

```bash
hop3 system status
```

### API Endpoints

After installation, the Hop3 server is reachable at:

- `https://<server-ip>/rpc` - JSON-RPC API endpoint (used by the CLI and TUI)
- `https://<server-ip>/dashboard` - Web dashboard (the root URL `/` redirects here, or to `/auth/login` when not signed in)

If using Let's Encrypt with a domain:
- `https://hop3.example.com/rpc`

## Development and Testing

### Local Development

For testing installers with local package changes:

```bash
# CLI
python3 install-cli.py --local-path /path/to/hop3/packages/hop3-cli

# Server
sudo python3 install-server.py --local-path /path/to/hop3/packages/hop3-server
```

### Building the single-file installers

The `install-cli.py` and `install-server.py` scripts are generated from the `hop3-installer` package by the bundler. Regenerate them after changing the installer code:

```bash
# Build both into installer/
make build-installers

# Or invoke the bundler directly
uv run hop3-install bundle --all --output-dir dist/
uv run hop3-install bundle --type server --output install-server.py
```

### Automated installer tests

The installer's end-to-end tests live in `packages/hop3-installer/tests/c_e2e/` and exercise the CLI and server installers against real targets. Run them with:

```bash
make test-installer
```

### Vagrant Testing

A `Vagrantfile` at the repository root provisions a clean Ubuntu VM (the repository is synced to `/vagrant`):

```bash
# Start the VM and SSH in
vagrant up
vagrant ssh

# Inside the VM, test against local package changes
# (run `make build-installers` on the host first to generate installer/)
python3 /vagrant/installer/install-cli.py --local-path /vagrant/packages/hop3-cli
sudo python3 /vagrant/installer/install-server.py --local-path /vagrant/packages/hop3-server

# Destroy the VM when done
vagrant destroy -f
```

## Architecture

Both installers follow the same design principles:

### Single-File Distribution

Each installer is a self-contained Python script that can be:
- Downloaded and executed directly
- Piped through `python3 -` for one-liner installation
- Inspected before running (no hidden downloads)

### Standard Library Only

No external dependencies beyond Python's standard library:
- `argparse` for CLI parsing
- `subprocess` for running commands
- `pathlib` for file operations
- `threading` for spinner animation

### Visual Feedback

- Step indicators: `[1/5]`, `[2/5]`, etc.
- Spinner animation for long operations
- Color-coded output (success/warning/error)
- Graceful degradation when not running in a TTY

### Environment Variable Support

All options can be set via environment variables, enabling:
- CI/CD integration
- Automation scripts
- Configuration management tools

### Error Handling

- Clear error messages with actionable suggestions
- Non-zero exit codes on failure
- Graceful handling of Ctrl+C interrupts

## Troubleshooting

### Python Version Too Old

```
Error: Python 3.10+ required
Found: Python 3.8.10
```

Install a newer Python:
```bash
# Ubuntu/Debian
sudo apt install python3.11

# Fedora
sudo dnf install python3.11

# macOS
brew install python@3.11
```

### venv Module Not Found

```
Error: Python venv module not found
```

Install the venv module:
```bash
# Ubuntu/Debian
sudo apt install python3-venv

# Fedora
sudo dnf install python3-pip  # venv included
```

### Permission Denied (Server Installer)

```
Error: This installer must be run as root
```

Run with sudo:
```bash
sudo python3 install-server.py
```

### Network Issues During Git Install

If `--git` fails due to network issues:
```bash
# Try PyPI instead
python3 install-cli.py

# Or download the repo manually and use --local-path
git clone https://github.com/abilian/hop3.git
python3 install-cli.py --local-path ./hop3/packages/hop3-cli
```

## License

Apache-2.0 - Copyright (c) 2025, Abilian SAS
