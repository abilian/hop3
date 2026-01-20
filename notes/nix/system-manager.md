# Hop3 with System-Manager on Ubuntu

[System-manager](https://github.com/numtide/system-manager) enables NixOS-style declarative system configuration on non-NixOS distributions like Ubuntu. Version 1.0 was released in January 2025.

## Prerequisites

- Ubuntu with Nix installed and flakes enabled
- Root access for system-manager switch

## Installation

### 1. Install system-manager

```bash
nix profile install github:numtide/system-manager
```

Ensure it's in your PATH:

```bash
export PATH="$HOME/.nix-profile/bin:$PATH"
```

### 2. Create hop3 user

System-manager doesn't manage users yet, so create the hop3 user manually:

```bash
sudo useradd -r -m -d /home/hop3 -s /bin/bash hop3
```

### 3. Initialize system-manager

```bash
system-manager init
```

This creates `~/.config/system-manager/` with starter files.

### 4. Configure for Hop3

Replace `~/.config/system-manager/flake.nix`:

```nix
{
  description = "Hop3 System Manager configuration";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    system-manager = {
      url = "github:numtide/system-manager";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    hop3 = {
      url = "github:abilian/hop3";  # or path:/path/to/hop3
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, system-manager, hop3, ... }:
    let
      system = "aarch64-linux";  # or "x86_64-linux"
    in
    {
      systemConfigs.default = system-manager.lib.makeSystemConfig {
        modules = [ ./system.nix ];
        extraSpecialArgs = {
          inherit hop3;
          hop3Pkgs = hop3.packages.${system};
        };
      };
    };
}
```

Replace `~/.config/system-manager/system.nix`:

```nix
{ lib, pkgs, hop3Pkgs, ... }:

let
  cfg = {
    user = "hop3";
    group = "hop3";
    homeDir = "/home/hop3";
    host = "127.0.0.1";
    port = 8000;
  };
in
{
  config = {
    nixpkgs.hostPlatform = "aarch64-linux";  # or "x86_64-linux"

    # Create hop3 directories
    systemd.tmpfiles.rules = [
      "d ${cfg.homeDir}/apps 0750 ${cfg.user} ${cfg.group} -"
      "d ${cfg.homeDir}/nginx 0750 ${cfg.user} ${cfg.group} -"
      "d ${cfg.homeDir}/uwsgi-available 0750 ${cfg.user} ${cfg.group} -"
      "d ${cfg.homeDir}/uwsgi-enabled 0750 ${cfg.user} ${cfg.group} -"
      "d ${cfg.homeDir}/logs 0750 ${cfg.user} ${cfg.group} -"
    ];

    # Hop3 server systemd service
    systemd.services.hop3-server = {
      description = "Hop3 PaaS Server";
      after = [ "network.target" ];
      wantedBy = [ "multi-user.target" ];

      serviceConfig = {
        Type = "simple";
        User = cfg.user;
        Group = cfg.group;
        WorkingDirectory = cfg.homeDir;

        ExecStart = "${hop3Pkgs.hop3-server}/bin/hop3-server serve --host ${cfg.host} --port ${toString cfg.port}";

        Restart = "on-failure";
        RestartSec = "5";

        Environment = [
          "HOP3_HOME=${cfg.homeDir}"
          "HOP3_DATABASE_URL=sqlite:///${cfg.homeDir}/hop3.db"
        ];

        # Security hardening
        NoNewPrivileges = "true";
        ProtectSystem = "strict";
        ProtectHome = "read-only";
        ReadWritePaths = cfg.homeDir;
        PrivateTmp = "true";
      };
    };

    # Add hop3-cli to system packages
    environment.systemPackages = [
      hop3Pkgs.hop3-cli
    ];
  };
}
```

### 5. Build and apply

```bash
cd ~/.config/system-manager

# Build first (optional, to check for errors)
system-manager build --flake .

# Apply configuration (requires sudo)
sudo system-manager switch --flake .
```

## Managing the Service

```bash
# Check status
sudo systemctl status hop3-server

# View logs
sudo journalctl -u hop3-server -f

# Restart
sudo systemctl restart hop3-server

# Stop
sudo systemctl stop hop3-server
```

## Updating Configuration

After modifying `system.nix`:

```bash
cd ~/.config/system-manager

# Preview changes
system-manager build --flake .

# Apply changes
sudo system-manager switch --flake .
```

## What System-Manager Manages

| Resource | Supported | Notes |
|----------|-----------|-------|
| systemd services | ✅ | Full support |
| /etc files | ✅ | Via environment.etc |
| tmpfiles (directories) | ✅ | Via systemd.tmpfiles |
| System packages | ✅ | Via environment.systemPackages |
| Users/groups | ❌ | Coming soon, create manually |
| Secrets | ❌ | Coming soon |

## Customization

Edit `system.nix` to customize:

```nix
cfg = {
  user = "hop3";
  group = "hop3";
  homeDir = "/home/hop3";
  host = "0.0.0.0";      # Bind to all interfaces
  port = 8080;           # Different port
};
```

## Troubleshooting

### "hop3 user does not exist"

Create the user first:
```bash
sudo useradd -r -m -d /home/hop3 -s /bin/bash hop3
```

### Service fails to start

Check logs:
```bash
sudo journalctl -u hop3-server -e
```

Common issues:
- Config initialization error (hop3-server tries to load config at import time)
- Database path not writable
- Port already in use

### Permission denied on /home/hop3

Fix ownership:
```bash
sudo chown -R hop3:hop3 /home/hop3
```

### system-manager command not found

Add to PATH:
```bash
export PATH="$HOME/.nix-profile/bin:$PATH"
```

## References

- [System-Manager 1.0 Announcement](https://numtide.com/blog/system-manager-1-0)
- [System-Manager GitHub](https://github.com/numtide/system-manager)
- [System-Manager Documentation](https://system-manager.net/)
