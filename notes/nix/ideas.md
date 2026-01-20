# Hop3 Deployment Architecture: Isolation Strategies

This document analyzes deployment options for Hop3 across different environments, focusing on isolation between applications.

## Understanding Isolation Layers

| Layer | What | Risk if Shared |
|-------|------|----------------|
| **Packages/Binaries** | Executables, libraries | App A modifies App B's code |
| **Runtime Data** | Databases, uploads, logs | Data leakage, corruption |
| **Processes** | Running application | Memory access, signals |
| **Network** | Ports, connections | Eavesdropping, spoofing |
| **Filesystem** | Read/write access | Arbitrary file access |

---

## 1. Traditional Installation (Ubuntu/Debian)

### Current State

- Single `hop3` user owns everything
- Apps run as `hop3` user (poor isolation) or in Docker containers (better isolation)
- Root needed for: package installation, nginx config, system services
- hop3 user for: app deployment, app runtime

### Isolation Options

#### Option A: Dedicated Users Per App

```
hop3 (orchestrator)
├── hop3-myapp1 (app runtime)
├── hop3-myapp2 (app runtime)
└── hop3-myapp3 (app runtime)
```

**Pros:**
- Standard Unix isolation (50+ years proven)
- Each app can only access its own files
- systemd can enforce user separation

**Cons:**
- User creation requires root (or pre-created pool)
- UID limits (~65k users, not a real issue)
- More complex permission management

#### Option B: Pre-allocated User Pool

Create users at install time:

```bash
# During hop3-install server
for i in $(seq 1 100); do
  useradd -r -M -s /usr/sbin/nologin "hop3-app${i}"
done
```

When deploying an app, assign next available user. This avoids needing root at deploy time.

#### Option C: systemd DynamicUser

```ini
[Service]
DynamicUser=yes
StateDirectory=hop3/apps/myapp
```

systemd creates transient users automatically. State persists in `/var/lib/hop3/apps/myapp/`.

**Pros:** No user management
**Cons:** User ID changes on restart (breaks some apps)

#### Option D: Linux Namespaces (without Docker)

systemd provides sandboxing:

```ini
[Service]
PrivateUsers=yes
PrivateNetwork=yes
ProtectHome=yes
ProtectSystem=strict
```

This gives container-like isolation without Docker.

---

## 2. Nix on Non-NixOS (Ubuntu + system-manager)

### Key Insight: /nix/store is Safe to Share

The `/nix/store` is **read-only** and **content-addressed**:
- Path `/nix/store/abc123-foo-1.0` is immutable
- Apps **cannot** modify each other's packages by design
- Sharing the store is safe and efficient (deduplication via hard links)

**"Can app A mess with app B's packages?"** → **No, by Nix design.**

The isolation question is about **runtime**, not packages.

### Package Management Options

#### Single /nix/store (recommended)

```
/nix/store/
├── abc123-python-3.12/
├── def456-myapp1-deps/
├── ghi789-myapp2-deps/
└── ...
```

Each app has its own "closure" (set of dependencies), but they share common packages (python, openssl, etc.). This is:
- Space efficient
- Safe (read-only store)
- Standard Nix practice

#### Separate Nix instances (not recommended)

- Would require multiple `/nix` directories
- Breaks sharing/deduplication
- No real benefit since store is already isolated

### Runtime Isolation Options

#### Option A: Separate users (same as traditional)

```nix
# system.nix for system-manager
systemd.services.hop3-app-myapp1 = {
  serviceConfig = {
    User = "hop3-app1";
    Group = "hop3-app1";
    # ...
  };
};
```

#### Option B: Nix-built OCI containers

```nix
# In flake.nix
hop3-myapp-image = pkgs.dockerTools.buildImage {
  name = "hop3-myapp";
  config.Cmd = [ "${myapp}/bin/myapp" ];
};
```

**Pros:**
- Reproducible images (Nix builds them)
- Full container isolation
- Can run with Docker or Podman

#### Option C: systemd sandboxing

```nix
systemd.services.hop3-app-myapp1.serviceConfig = {
  DynamicUser = true;
  PrivateTmp = true;
  ProtectSystem = "strict";
  ProtectHome = true;
  NoNewPrivileges = true;
  # etc.
};
```

### system-manager Capabilities

system-manager manages:
- systemd services (with all sandboxing options)
- /etc files
- tmpfiles (directories)
- System packages in PATH
- Users (coming soon, currently manual)

---

## 3. NixOS

NixOS provides the most options for isolation.

### Option A: Declarative Users + systemd Sandboxing

```nix
# configuration.nix
users.users.hop3-app1 = {
  isSystemUser = true;
  group = "hop3-app1";
};

systemd.services.hop3-app-myapp1 = {
  serviceConfig = {
    User = "hop3-app1";
    DynamicUser = false;  # Use declared user
    # sandboxing options...
  };
};
```

### Option B: NixOS Containers (systemd-nspawn)

```nix
containers.myapp1 = {
  autoStart = true;
  privateNetwork = true;
  hostAddress = "192.168.100.1";
  localAddress = "192.168.100.2";

  config = { pkgs, ... }: {
    services.myapp.enable = true;
    # Full NixOS config for this container
  };
};
```

**Pros:**
- Strong isolation (network, filesystem, process namespaces)
- Shares `/nix/store` via bind mount (efficient!)
- Each container is a mini-NixOS
- Declarative

**Cons:**
- More overhead than plain services
- More complex networking

### Option C: OCI Containers via Podman/Docker

```nix
virtualisation.oci-containers.containers.myapp1 = {
  image = "localhost/hop3-myapp:latest";  # Built by Nix
  ports = ["8080:8080"];
  volumes = ["/var/lib/hop3/apps/myapp:/data"];
};
```

---

## Summary: Recommended Architecture

| Scenario | Package Isolation | Runtime Isolation | Recommended |
|----------|------------------|-------------------|-------------|
| **Traditional** | None (shared system packages) | Docker or dedicated users | Dedicated users + systemd sandboxing |
| **Nix on Ubuntu** | Automatic (Nix store) | Need explicit | system-manager + dedicated users + sandboxing |
| **NixOS** | Automatic (Nix store) | Full options | NixOS containers or systemd sandboxing |

### Key Decisions for Hop3

1. **Pre-allocated user pool**: Create users at install time (`hop3-app001` to `hop3-app100`). Avoids root at deploy time.

2. **systemd sandboxing by default**: All apps get `PrivateTmp`, `ProtectSystem`, `NoNewPrivileges`, etc.

3. **Optional container mode**: For high-security needs, deploy in NixOS containers or Docker.

4. **Single /nix/store**: Always share the store. It's safe and efficient.

---

## Open Questions

- How many pre-allocated users? 100? Configurable?
- Should user pool creation be part of `hop3-install server` or a separate step?
- How to handle user assignment (first available, or hash-based on app name)?
- What systemd sandboxing options should be default vs. opt-in?
- Should we support microVMs (via microvm.nix) for strongest isolation?
