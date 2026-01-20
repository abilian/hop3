# Hop3 NixOS Module

This document describes how to deploy Hop3 on NixOS using the provided module.

## Quick Start

Add the Hop3 flake to your NixOS configuration:

```nix
# flake.nix
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    hop3.url = "github:abilian/hop3";  # or path to local checkout
  };

  outputs = { self, nixpkgs, hop3 }: {
    nixosConfigurations.myserver = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        hop3.nixosModules.default
        ./configuration.nix
      ];
    };
  };
}
```

Then enable Hop3 in your configuration:

```nix
# configuration.nix
{
  services.hop3 = {
    enable = true;
    nginx.enable = true;
    nginx.virtualHost = "hop3.example.com";
  };
}
```

## Configuration Options

### Basic Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enable` | bool | `false` | Enable Hop3 PaaS server |
| `package` | package | hop3-server | The hop3-server package to use |
| `user` | string | `"hop3"` | User account for service |
| `group` | string | `"hop3"` | Group for service |
| `homeDir` | path | `/home/hop3` | Home directory for data |
| `host` | string | `"127.0.0.1"` | Bind address |
| `port` | int | `8000` | API server port |
| `secretKeyFile` | path | `null` | Path to JWT secret key file |

### Database Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `database.type` | enum | `"sqlite"` | `"sqlite"` or `"postgresql"` |
| `database.createLocally` | bool | `true` | Create PostgreSQL DB automatically |
| `database.name` | string | `"hop3"` | Database name |

### Nginx Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `nginx.enable` | bool | `false` | Enable Nginx reverse proxy |
| `nginx.virtualHost` | string | `"hop3.localhost"` | Virtual host name |
| `nginx.enableSSL` | bool | `false` | Enable ACME SSL certificates |

### Other Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `openFirewall` | bool | `false` | Open HTTP/HTTPS ports |

## Example Configurations

### Minimal (SQLite, no proxy)

```nix
{
  services.hop3.enable = true;
}
```

Access at `http://localhost:8000`.

### With Nginx Reverse Proxy

```nix
{
  services.hop3 = {
    enable = true;
    nginx = {
      enable = true;
      virtualHost = "hop3.example.com";
    };
    openFirewall = true;
  };
}
```

### With PostgreSQL

```nix
{
  services.hop3 = {
    enable = true;
    database = {
      type = "postgresql";
      createLocally = true;
    };
  };
}
```

### Production Setup (PostgreSQL + SSL)

```nix
{
  services.hop3 = {
    enable = true;

    database = {
      type = "postgresql";
      createLocally = true;
    };

    secretKeyFile = "/run/secrets/hop3-jwt-key";

    nginx = {
      enable = true;
      virtualHost = "hop3.example.com";
      enableSSL = true;
    };

    openFirewall = true;
  };

  # Required for ACME
  security.acme = {
    acceptTerms = true;
    defaults.email = "admin@example.com";
  };
}
```

### With sops-nix for Secrets

```nix
{
  sops.secrets.hop3-jwt-key = {
    owner = "hop3";
    group = "hop3";
  };

  services.hop3 = {
    enable = true;
    secretKeyFile = config.sops.secrets.hop3-jwt-key.path;
  };
}
```

## Directory Structure

The module creates the following structure:

```
/home/hop3/
├── apps/           # Application deployments
├── nginx/          # Nginx configs for apps
├── uwsgi-available/
├── uwsgi-enabled/
├── logs/           # Log files
└── hop3.db         # SQLite database (if used)
```

## Service Management

```bash
# Check status
systemctl status hop3-server

# View logs
journalctl -u hop3-server -f

# Restart service
systemctl restart hop3-server
```

## Troubleshooting

### Service fails to start

Check logs:
```bash
journalctl -u hop3-server -e
```

Common issues:
- Missing secret key file
- Database connection failed
- Port already in use

### Database issues

For PostgreSQL, ensure the service is running:
```bash
systemctl status postgresql
```

Check if database exists:
```bash
sudo -u postgres psql -l | grep hop3
```

### Permission denied

Ensure home directory permissions:
```bash
ls -la /home/hop3
```

The directory should be owned by `hop3:hop3` with mode `0750`.
