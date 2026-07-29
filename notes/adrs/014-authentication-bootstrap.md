# ADR 014: Authentication Bootstrap Process

- **Status**: Final
- **Type**: Feature
- **Created**: 2025-11-28
- **Updated**: 2026-06-23
- **Related-ADRs**: [012](./012-mfa.md), [018](./018-cli-architecture.md), [036](./036-cli-ergonomics.md)

## Context and Goals

Hop3 uses JWT-based bearer token authentication for API access. The current authentication flow requires users to:

1. Register an account (`hop3 auth register`)
2. Log in to receive a JWT token (`hop3 login`, which saves it for you)
3. The token is stored in `~/.config/hop3-cli/config.toml`
4. Include the token in subsequent requests via `Authorization: Bearer <token>` header

However, there is a bootstrap problem: **How do we create the first admin user and obtain the initial authentication token?**

### The Security Principle

> **Only someone with server access should be able to create the first admin account.**

This is non-negotiable for remote servers. The verification of "server access" can be:
- SSH access (can run commands on the server)
- Physical/console access
- Access to server configuration files

"First-user-becomes-admin" violates this principle because anyone who can reach the server's network endpoint could race to become admin.

### Use Cases

| Use Case | Actor | Context | Goal |
|----------|-------|---------|------|
| **UC1** | Sysadmin | Fresh server, SSH access | Create admin, configure CLI |
| **UC2** | Automation (Ansible) | IaC deployment | Bootstrap non-interactively |
| **UC3** | Existing admin | Server running | Add team members |
| **UC4** | Admin (locked out) | Lost token/password | Regain access |

---

## Decision

We implement **Option A: Server-Side CLI** as the primary mechanism, with **SSH-Assisted Bootstrap** as a convenience enhancement.

### Summary

1. **`hop3-server admin:create`** - Server-side command to create admin users
2. **`hop3 init --ssh`** - Client-side command that automates the workflow over SSH

---

## Solution: Server-Side CLI (Option A)

### Commands

**Server-side (hop3-server):**
```bash
hop3-server admin:create <username> <email> [--password-stdin]
    Create admin user and display API token.
    Password read from stdin for security.

hop3-server admin:token <username>
    Generate new API token for existing user.

hop3-server admin:list
    List all users with admin status.
```

### Manual Workflow

```bash
# 1. SSH to server
ssh root@my-server.com

# 2. Create admin account (password prompted or via stdin)
hop3-server admin:create myuser me@example.com
# Enter password: ********
# Output:
# Admin user 'myuser' created.
# Token: eyJhbGciOiJI...

# 3. On local machine, configure CLI
hop3 settings set server https://my-server.com
hop3 settings set token eyJhbGciOiJI...

# 4. Verify
hop3 auth whoami
```

### Security Considerations

1. **Password handling**: Use `--password-stdin` to avoid password in process list
2. **Token display**: Token shown once; user must save it
3. **Access control**: Only users who can run `hop3-server` can create admins

---

## Enhancement: SSH-Assisted Bootstrap (Option A+)

For users with SSH access, we provide a single-command convenience that automates the 6-step manual process.

### Commands

**Client-side (hop3):**
```bash
# Full bootstrap - create new admin user
hop3 init --ssh user@server

# Get token for existing user (lost token, new machine)
hop3 login --ssh user@server
```

### User Experience

**First-time setup:**
```
$ hop3 init --ssh root@my-server.com

Connecting to my-server.com...
✓ Connected

Admin username: admin
Admin email: admin@company.com
Admin password: ********
Confirm password: ********

Creating admin user...
✓ Admin user 'admin' created

Server URL [https://my-server.com]:
✓ Configuration saved to ~/.config/hop3-cli/config.toml

You're all set! Try:
  hop3 status       # Check server status
  hop3 apps         # List applications
```

**Existing server, new machine:**
```
$ hop3 login --ssh root@my-server.com

Connecting to my-server.com...
✓ Connected

Username: admin
Generating new token...
✓ Token saved to ~/.config/hop3-cli/config.toml

Welcome back, admin!
```

**Non-interactive (CI/automation):**
```bash
echo "$ADMIN_PASSWORD" | hop3 init \
  --ssh deploy@my-server.com \
  --username admin \
  --email admin@company.com \
  --url https://my-server.com \
  --password-stdin \
  --yes
```

### How It Works

1. CLI opens SSH connection to server
2. Runs `hop3-server admin:create` remotely
3. Captures the token from stdout
4. Configures local CLI with server URL + token
5. Closes SSH connection

### Comparison: Manual vs SSH-Assisted

| Step | Manual (6 steps) | SSH-Assisted (1 command) |
|------|------------------|--------------------------|
| 1 | `ssh root@server` | `hop3 init --ssh root@server` |
| 2 | `hop3-server admin:create ...` | (automated) |
| 3 | Copy token from output | (automated) |
| 4 | `hop3 settings set server ...` | (automated) |
| 5 | `hop3 settings set token ...` | (automated) |
| 6 | `exit` SSH | (automated) |

---

## Alternatives Considered

### Option B: Bootstrap Token in Environment

Generate a one-time token during installation stored in `/etc/hop3/bootstrap-token`.

**Rejected because:**
- Token must be securely transmitted from server to client
- One-time use complexity (what if it fails mid-way?)
- Option A is simpler and equally secure

**Future consideration:** Could be added for automation scenarios.

### Option C: Default Seed User

Create default `admin/admin123` during database migration.

**Rejected because:**
- Well-known credentials are a security risk
- Requires forced password change mechanism
- Poor security posture

### Option D: First-User-Becomes-Admin

Allow first registration to automatically become admin.

**Rejected because:**
- Race condition vulnerability on remote servers
- Anyone who can reach the network endpoint could become admin
- Violates the security principle

---

## Implementation

The server-side CLI provides the `hop3-server` entry point in `pyproject.toml`:

```toml
[project.scripts]
hop3-server = "hop3.cli.main:main"
```

**Server-side admin:create:**
```python
import click
from hop3.orm import User
from hop3.server.security.tokens import create_token

@click.command()
@click.argument('username')
@click.argument('email')
@click.option('--password-stdin', is_flag=True, help='Read password from stdin')
def create_admin(username: str, email: str, password_stdin: bool):
    """Create an admin user and display API token."""
    if password_stdin:
        password = sys.stdin.read().strip()
    else:
        password = click.prompt('Password', hide_input=True, confirmation_prompt=True)

    # Create user with direct database access
    db = get_database_session()
    user = User(username=username, email=email)
    user.set_password(password)
    user.is_admin = True
    user.active = True
    db.add(user)
    db.commit()

    # Generate token
    token = create_token(username, scopes=['admin', 'authenticated'])

    click.echo(f"Admin user '{username}' created.")
    click.echo(f"Token: {token}")
```

**Client-side init --ssh:**
```python
import subprocess
import shlex

def init_via_ssh(ssh_target: str, username: str, email: str, password: str, server_url: str):
    """Bootstrap Hop3 by running admin:create over SSH."""
    remote_cmd = f"hop3-server admin:create {shlex.quote(username)} {shlex.quote(email)} --password-stdin"

    result = subprocess.run(
        ["ssh", ssh_target, remote_cmd],
        input=password.encode(),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise BootstrapError(f"Failed to create admin: {result.stderr}")

    token = extract_token(result.stdout)

    config = get_config()
    config.save({"server": server_url, "api_token": token})

    return token
```

---

## Web Portal Authentication

The same user created by `hop3-server admin:create` can:
1. Use CLI with the API token
2. Login to web portal with username/password

No separate bootstrap needed for web portal.

---

## Backwards Compatibility

The bootstrap mechanism is additive and layers on top of the existing public auth flow, which is unchanged:

- `auth register` is public (creates non-admin users)
- `auth get-token` is public (verifies credentials and returns a token)

The bootstrap introduces, without breaking anything above:

1. **The `hop3-server` CLI**: a server-side entry point.
2. **The `hop3 init --ssh` command**: a client-side bootstrap convenience.

Existing users and tokens remain valid, and no existing command changes behaviour.

### Update (2026-06): login/logout are client-side; `auth get-token` is the primitive

The interactive login flow (`hop3 login`, and its canonical spelling `hop3 auth login`) is handled entirely **client-side**: it bootstraps over SSH, accepts token URLs and magic links (`--web`), prompts for a password, and saves the resulting token to the active context. `hop3 logout` / `hop3 auth logout` mirror it (revoke the token server-side, then clear it locally). `login`/`logout` are registered as short-form aliases of `auth login`/`auth logout`.

The public server RPC that verifies a username + password and returns a token (originally named `auth login` in this ADR) is now **`auth get-token`**. It simply prints the token, for scripts and automation; the interactive login flow calls it under the hood. See [ADR 036](./036-cli-ergonomics.md) (CLI ergonomics and command surface) for the alias and command-surface rationale.

---

## Consequences

### Benefits

- **Secure by design**: Requires server access to create admin
- **Simple implementation**: Direct database access, no HTTP auth complexity
- **Familiar pattern**: Similar to Django's `createsuperuser`
- **Flexible**: Works for bootstrap, recovery, and team onboarding
- **Convenient**: SSH-assisted mode reduces 6 steps to 1 command
- **Automation-friendly**: Non-interactive mode with `--password-stdin`

### Drawbacks

- **Requires SSH for remote servers**: Required by the security principle
- **Two implementations**: Server CLI + client SSH wrapper

### Trade-offs

- **Security over convenience**: Requiring server access
- **Two modes**: Manual for simplicity, SSH-assisted for convenience

---

## References

- Django: `python manage.py createsuperuser`
- Rails: `rails console` + `User.create!(...)`
- Heroku: API key in dashboard, then `heroku login`
- Kubernetes: `kubectl` config with kubeconfig file

## Related ADRs

- [ADR 010](./010-security-and-resilience.md): Security and Resilience Enhancements
- [ADR 012](./012-mfa.md): Multi-Factor Authentication (MFA)

## Implementation References

- Token management: `packages/hop3-server/src/hop3/server/security/tokens.py`
- Auth commands: `packages/hop3-server/src/hop3/commands/auth.py`
- CLI config: `packages/hop3-cli/src/hop3_cli/config.py`

---

## Appendix: Extended Alternatives Analysis

### Comparison Matrix

| Criteria | Option 1: CLI | Option 2: Bootstrap Token | Option 3: Seed User | Option 4: Conditional |
|----------|---------------|---------------------------|---------------------|-----------------------|
| Security | ✅ High | ⚠️ Medium | ❌ Low | ⚠️ Medium |
| Automation | ⚠️ Requires SSH | ✅ Fully automated | ✅ Fully automated | ⚠️ Requires coordination |
| Auditability | ✅ Explicit | ✅ Token generation logged | ⚠️ Default credentials | ❌ Implicit |
| User Experience | ⚠️ Requires server access | ✅ Direct | ✅ Simple | ✅ Self-service |
| Implementation | ✅ Simple | ⚠️ Token management | ✅ Simple | ⚠️ Race conditions |

### Risk Analysis

#### Security Risks

- **Privilege Escalation**: Bootstrap mechanism provides elevated privileges that could be abused if not properly secured
- **Credential Exposure**: Default credentials or bootstrap tokens could be leaked or discovered
- **Race Conditions**: Multiple simultaneous bootstrap attempts could create security vulnerabilities

**Mitigation:**
- Implement bootstrap mechanism with time limits or usage counts
- Require immediate password/token rotation after bootstrap
- Log all bootstrap operations for audit
- Consider requiring confirmation step for bootstrap operations

#### Operational Risks

- **Locked Out Admin**: If bootstrap process fails, admin may be locked out
- **Token Loss**: If initial token is lost before being saved, recovery process needed
- **Documentation Gap**: Users may not find or follow bootstrap instructions

**Mitigation:**
- Provide multiple recovery mechanisms
- Clear error messages with recovery instructions
- Comprehensive documentation with examples

### Option Details

#### Option 2: Bootstrap Token in Environment (Not Selected)

Generate a special bootstrap token during server installation:

**How it works:**
- Installation script generates a random bootstrap token
- Token stored in `/etc/hop3/bootstrap.token` or `HOP3_BOOTSTRAP_TOKEN` env var
- Bootstrap token has elevated privileges to create first admin
- Must be used to register initial admin, then should be rotated/deleted

**Characteristics:**
- Automated bootstrap possible
- Token is a shared secret requiring secure handling
- Needs mechanism to rotate/revoke after first use
- Good for automated deployment pipelines

#### Option 3: Database Migration with Seed User (Not Selected)

Create a default admin user during initial database migration:

**How it works:**
- Initial migration creates `admin` user with default password
- Credentials documented in installation guide
- User must change password on first login
- Login returns token for subsequent operations

**Characteristics:**
- Zero-friction setup
- **Security concern**: Well-known default credentials
- Requires prominent documentation and warnings
- Password change enforcement critical

#### Option 4: Conditional Public Registration (Not Selected)

Allow first user registration without authentication:

**How it works:**
- If database has zero users, allow `auth:register --admin` without token
- Once first admin exists, all `auth:register` requires authentication or admin approval
- First user automatically gets admin privileges

**Characteristics:**
- Self-service bootstrap
- **Security concern**: Race condition if multiple users register simultaneously
- Requires network isolation during initial setup
- Simple for single-admin deployments
