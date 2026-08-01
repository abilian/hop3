# Server Setup Guide

This guide explains how to set up Hop3 on a server using the installer script. The installer is a standalone Python script that automates the installation and configuration process.

## Prerequisites

- A server running Ubuntu 24.04 or 26.04 LTS (Debian-based distributions also supported)
- Root access to the server via SSH
- Python 3.10+ on the server
- A domain name pointing to your server (required for secure HTTPS; without it, admin UI uses unencrypted HTTP on port 8000)

## Quick Install

### One-liner (from PyPI)

```bash
curl -LsSf https://hop3.cloud/install-server.py | sudo python3 -
```

### With Admin Domain (Recommended)

For secure HTTPS access to the admin UI, specify a domain:

```bash
curl -LsSf https://hop3.cloud/install-server.py | sudo python3 - --domain hop3.example.com
```

This will:
- Configure nginx to serve the admin UI at `https://hop3.example.com/`
- Request a Let's Encrypt SSL certificate automatically
- Store the admin domain in the server configuration

## Installation Options

### From Git (Development)

Install from a specific git branch:

```bash
sudo python3 install-server.py --from git --branch main
```

### From Local Path

For development or testing with local code:

```bash
sudo python3 install-server.py --path /path/to/hop3-server
```

### All Options

| Option | Description |
|--------|-------------|
| `--domain DOMAIN` | Domain for admin UI (enables Let's Encrypt SSL) |
| `--acme-email EMAIL` | Email for Let's Encrypt registration (required when using `--domain`) |
| `--with FEATURES` | Comma-separated optional features: `mysql`, `redis`, `docker`, `nix`, `s3`, or `all` |
| `--version VERSION` | Install specific version from PyPI |
| `--pre` | Allow pre-release versions from PyPI |
| `--from git` | Install from git repository |
| `--branch BRANCH` | Git branch to install (default: main) |
| `--path PATH` | Install from local directory |
| `--force` | Force reinstall |
| `--skip-deps` | Skip system dependency installation |
| `--skip-nginx` | Skip nginx configuration |
| `--skip-postgres` | Skip PostgreSQL setup |
| `--skip-acme` | Skip ACME/Let's Encrypt setup |
| `--verbose` | Show detailed output |

## What the Installer Does

1. **System Dependencies**: Installs required packages (nginx, PostgreSQL, Python dev tools, etc.)
2. **User Setup**: Creates `hop3` user and group
3. **Virtual Environment**: Creates Python venv at `/home/hop3/venv`
4. **Package Installation**: Installs hop3-server
5. **Initial Setup**: Runs `hop3-server setup` to create directories and config
6. **SSH Keys**: Copies root's SSH keys to hop3 user
7. **Systemd Services**: Configures hop3-server and uwsgi-hop3 services
8. **SSL Certificates**: Generates self-signed cert (or Let's Encrypt if domain provided)
9. **Nginx**: Configures reverse proxy for the admin UI and API
10. **PostgreSQL**: Creates hop3 database and user, configures for Docker access
11. **Server Config**: Writes `/home/hop3/hop3-server.toml` with settings

## Admin UI Access

### With Domain (Recommended)

When you install with `--domain hop3.example.com`:

- **Admin UI**: `https://hop3.example.com/`
- **API (RPC)**: `https://hop3.example.com/rpc`
- **SSL**: Let's Encrypt certificate (auto-renewed)

Deployed applications use their own hostnames (e.g., `myapp.example.com`).

### Without Domain

Without `--domain`, the admin UI is only accessible directly on port 8000:

- **Admin UI**: `http://<server-ip>:8000/` (unsecured)
- **API (RPC)**: `https://<server-ip>/rpc` (self-signed cert)

> **Warning**: Port 8000 access is unencrypted. Use `--domain` for production deployments.

For development/testing, you can use SSH tunneling:

```bash
ssh -L 8000:127.0.0.1:8000 root@your-server
# Then access: http://localhost:8000/
```

## Post-Installation Steps

### Create Admin User

Before using Hop3, create an admin user. The easiest way is SSH-assisted bootstrap from your workstation:

```bash
hop3 init --ssh root@your-server.com
```

This will:
1. Connect to your server via SSH
2. Prompt for admin username, email, and password
3. Create the admin user on the server
4. Save the API token to `~/.config/hop3-cli/config.toml`

Example session:
```
$ hop3 init --ssh root@my-server.com

Connecting to my-server.com...
Server URL [https://my-server.com]:
Admin username: admin
Admin email: admin@company.com
Admin password: ********
Confirm password: ********

Admin user 'admin' created successfully.
Configuration saved to ~/.config/hop3-cli/config.toml

You're all set! Try:
  hop3 app list           # List applications
  hop3 auth whoami    # Check current user
```

### Alternative: Server-Side Commands

The installer does **not** create an admin user or print a token — you create
the first admin yourself. SSH in and run the `hop3-server` admin commands as the
`hop3` user (so the database stays owned by `hop3`, not `root`):

```bash
ssh root@your-server.com

# Create the first admin and print an API token:
sudo -u hop3 /home/hop3/venv/bin/hop3-server admin:create admin admin@example.com
#   ... enter a password when prompted, then copy the printed token.

# Issue a fresh token for an existing user:
sudo -u hop3 /home/hop3/venv/bin/hop3-server admin:token admin

# Set or change a password:
sudo -u hop3 /home/hop3/venv/bin/hop3-server admin:reset-password admin

# List users (sanity check):
sudo -u hop3 /home/hop3/venv/bin/hop3-server admin:list
```

Then log into the server from your local CLI with the token:

```bash
hop3 auth login --token <paste-token-here> --url https://your-server.com
```

> `hop3 auth login --ssh root@your-server.com` does all of the above in one step
> (SSH access ⇒ admin access): it runs `admin:ssh-token` on the server,
> auto-creating a default `admin` if none exists, and stores the token locally.

### Magic Links (passwordless Web UI login)

Once an [admin domain](#admin-ui-access) is configured, you can sign into the
Web UI without a password using a one-time magic link. From your workstation:

```bash
hop3 auth login --web root@your-server.com
```

This prints a `https://<admin-domain>/auth/magic/<token>` URL — open it in a
browser. The link expires after **5 minutes** and is single-use. To mint one
directly on the server:

```bash
sudo -u hop3 /home/hop3/venv/bin/hop3-server auth:magic-link admin
```

A magic link is only usable when the Web UI is reachable at a hostname — i.e.
when an admin domain is set (see [Admin UI Access](#admin-ui-access)).

### For Automation (CI/CD)

Use non-interactive mode:

```bash
echo "$ADMIN_PASSWORD" | hop3 init \
  --ssh deploy@my-server.com \
  --username admin \
  --email admin@company.com \
  --url https://my-server.com \
  --password-stdin \
  --yes
```

## Using the Demo Launcher

For testing and demonstrations, use the demo launcher:

```bash
# Basic demo (apps cleaned up after)
python demos/demo.py run --host <your-server-ip> demo01

# Keep apps running with admin domain
python demos/demo.py run --host <your-server-ip> --admin-domain hop3.example.com --keep demo01

# Use local code (development)
python demos/demo.py run --host <your-server-ip> --local --keep demo01
```

The demo launcher will:
- Install/update Hop3 on the target server
- Configure the admin domain (if specified)
- Create an admin user
- Deploy demo applications
- Show admin credentials and UI URL at the end

## Verification

After installation, verify services are running:

```bash
sudo systemctl status hop3-server
sudo systemctl status nginx
sudo systemctl status postgresql
```

Check logs:

```bash
sudo journalctl -u hop3-server -f
```

## Troubleshooting

### Services Not Starting

Check service status and logs:

```bash
sudo systemctl status hop3-server
sudo journalctl -u hop3-server --no-pager -n 50
```

### SSL Certificate Issues

For Let's Encrypt, ensure:
- Domain DNS points to your server's IP
- Ports 80 and 443 are open
- No other service is using port 80

To manually request a certificate:

```bash
sudo -u hop3 /home/hop3/.acme.sh/acme.sh --issue -d your-domain.com -w /var/www/html
```

### PostgreSQL Connection Issues

Verify PostgreSQL is configured for the hop3 user:

```bash
sudo -u hop3 psql -d hop3 -c "SELECT 1"
```

### Admin UI Shows 404

If using a domain and getting 404:
1. Verify nginx config: `sudo nginx -t`
2. Check nginx is proxying to hop3-server: `cat /etc/nginx/sites-available/hop3`
3. Ensure hop3-server is running on port 8000

### Bare Host Serves the Wrong App (or the Default Nginx Page)

**Symptom**: `http://your-server/` shows the default nginx welcome page, or
`https://your-server/` shows one of your deployed apps (with the wrong TLS
certificate) instead of the Hop3 Web UI.

**Cause**: the control plane isn't claiming the bare host. Each app's nginx
vhost matches only its own `server_name`, so a request to a host that matches no
app falls through to whichever vhost nginx loaded first — the distro default on
port 80, an arbitrary app on port 443. This happens on servers installed before
the control plane started pinning nginx's `default_server`.

**Fix**: redeploy. `hop3-deploy-server --host your-server.com` now makes
`your-server.com` the admin hostname automatically and pins the Hop3 control
plane as nginx's `default_server`, so the bare host — and any unmatched Host —
reaches the Web UI instead of a random app. To serve the Web UI on a *different*
hostname, pass it explicitly:

```bash
# Developer tool — a different admin hostname:
hop3-deploy-server --from local --host your-server.com --admin-domain admin.your-server.com

# Production installer (uses --domain):
curl -LsSf https://hop3.cloud/install-server.py | sudo python3 - --domain your-server.com
```

> The admin-domain step runs on every deploy, so a redeploy re-asserts the
> control-plane vhost and self-heals an older box — no `--clean` required.
> (On RHEL/Fedora the `default_server` pin is skipped to avoid clashing with the
> stock `nginx.conf`; the `server_name` match still routes the admin host.)

## Support

For additional help or to report issues:
- GitHub: [https://github.com/abilian/hop3/issues](https://github.com/abilian/hop3/issues)
- Documentation: [https://hop3.cloud/docs](https://hop3.cloud/docs)
