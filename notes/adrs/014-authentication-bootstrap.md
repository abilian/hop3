# ADR 014: Authentication Bootstrap Process

**Status**: Accepted
**Type**: Feature
**Created**: 2025-11-28
**Related-ADRs**: 012, 018

## Context and Goals

Hop3 uses JWT-based bearer token authentication for API access. The current authentication flow requires users to:

1. Register an account (`hop3 auth:register`)
2. Login to receive a JWT token (`hop3 auth:login`)
3. Store the token in `~/.config/hop3-cli/config.toml`
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

1. **`hop-server admin:create`** - Server-side command to create admin users
2. **`hop3 init --ssh`** - Client-side command that automates the workflow over SSH

---

## Solution: Server-Side CLI (Option A)

### Commands

**Server-side (hop-server):**
```bash
hop-server admin:create <username> <email> [--password-stdin]
    Create admin user and display API token.
    Password read from stdin for security.

hop-server admin:token <username>
    Generate new API token for existing user.

hop-server admin:list
    List all users with admin status.
```

### Manual Workflow

```bash
# 1. SSH to server
ssh root@my-server.com

# 2. Create admin account (password prompted or via stdin)
hop-server admin:create myuser me@example.com
# Enter password: ********
# Output:
# Admin user 'myuser' created.
# Token: eyJhbGciOiJI...

# 3. On local machine, configure CLI
hop3 settings set server https://my-server.com
hop3 settings set token eyJhbGciOiJI...

# 4. Verify
hop3 auth:whoami
```

### Security Considerations

1. **Password handling**: Use `--password-stdin` to avoid password in process list
2. **Token display**: Token shown once; user must save it
3. **Access control**: Only users who can run `hop-server` can create admins

---

## Enhancement: SSH-Assisted Bootstrap (Option A+)

For users with SSH access, we provide a single-command convenience that automates the entire 6-step manual process.

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
  --server https://my-server.com \
  --password-stdin \
  --yes
```

### How It Works

1. CLI opens SSH connection to server
2. Runs `hop-server admin:create` remotely
3. Captures the token from stdout
4. Configures local CLI with server URL + token
5. Closes SSH connection

### Comparison: Manual vs SSH-Assisted

| Step | Manual (6 steps) | SSH-Assisted (1 command) |
|------|------------------|--------------------------|
| 1 | `ssh root@server` | `hop3 init --ssh root@server` |
| 2 | `hop-server admin:create ...` | (automated) |
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

### Phase 1: Server-side CLI (Foundation)

**Files to create:**
```
packages/hop3-server/
├── src/hop3/
│   └── cli/
│       ├── __init__.py
│       ├── main.py          # Entry point for hop-server
│       └── admin.py         # Admin commands
```

**Entry point in pyproject.toml:**
```toml
[project.scripts]
hop-server = "hop3.cli.main:main"
```

### Phase 2: SSH-Assisted Bootstrap (Convenience)

**Files to create/modify:**
```
packages/hop3-cli/
├── src/hop3_cli/
│   └── commands/
│       └── init.py          # hop3 init --ssh command
```

### Implementation Details

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
    remote_cmd = f"hop-server admin:create {shlex.quote(username)} {shlex.quote(email)} --password-stdin"

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

The same user created by `hop-server admin:create` can:
1. Use CLI with the API token
2. Login to web portal with username/password

No separate bootstrap needed for web portal.

---

## Migration from Current State

### Current State
- `auth:register` is public (creates non-admin users)
- `auth:login` is public (returns token)
- No way to create first admin

### Changes
1. **Add `hop-server` CLI** - new entry point (additive)
2. **Add `hop3 init --ssh`** - new command (additive)
3. **Keep existing auth flow** - no breaking changes

### Backward Compatibility

- No breaking changes to existing auth flow
- New commands are additive
- Existing users/tokens remain valid

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

- **Requires SSH for remote servers**: But this is intentional for security
- **Two implementations**: Server CLI + client SSH wrapper

### Trade-offs

- **Security over convenience**: Chose requiring server access over easier but less secure options
- **Two modes**: Manual for simplicity, SSH-assisted for convenience

---

## References

- Django: `python manage.py createsuperuser`
- Rails: `rails console` + `User.create!(...)`
- Heroku: API key in dashboard, then `heroku login`
- Kubernetes: `kubectl` config with kubeconfig file

## Related ADRs

- ADR 010: Security and Resilience Enhancements
- ADR 012: Multi-Factor Authentication (MFA)

## Implementation References

- Token management: `packages/hop3-server/src/hop3/server/security/tokens.py`
- Auth commands: `packages/hop3-server/src/hop3/commands/auth.py`
- CLI config: `packages/hop3-cli/src/hop3_cli/config.py`

---

## Appendix: Original Discussion (Draft Phase)

*The following content was part of the original draft ADR and is preserved for historical reference.*

### Original Comparison Matrix

| Criteria | Option 1: CLI | Option 2: Bootstrap Token | Option 3: Seed User | Option 4: Conditional |
|----------|---------------|---------------------------|---------------------|-----------------------|
| Security | ✅ High | ⚠️ Medium | ❌ Low | ⚠️ Medium |
| Automation | ⚠️ Requires SSH | ✅ Fully automated | ✅ Fully automated | ⚠️ Requires coordination |
| Auditability | ✅ Explicit | ✅ Token generation logged | ⚠️ Default credentials | ❌ Implicit |
| User Experience | ⚠️ Requires server access | ✅ Seamless | ✅ Simple | ✅ Self-service |
| Implementation | ✅ Simple | ⚠️ Token management | ✅ Simple | ⚠️ Race conditions |

### Original Risk Analysis

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

### Original Option Details

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

### Original Action Items (From Draft)

1. **Decision Phase**: ✅ Completed
   - Review proposed options with team
   - Evaluate security implications of each approach
   - Consider deployment scenarios (bare metal, containers, cloud)
   - Select preferred option or hybrid approach

2. **Design Phase**: ✅ Completed
   - Document detailed authentication flow with bootstrap
   - Design API/CLI interface for chosen option
   - Plan security measures (token rotation, audit logging)
   - Define error handling and recovery procedures

3. **Implementation Phase**: ✅ Completed (Phase 1)
   - Implement server-side bootstrap mechanism
   - Add CLI commands for bootstrap operations
   - Implement audit logging for bootstrap events
   - Add tests for bootstrap scenarios

4. **Documentation Phase**: 🔄 In Progress
   - Update installation guide with bootstrap instructions
   - Document security best practices
   - Provide examples for common deployment scenarios
   - Create troubleshooting guide for bootstrap issues

5. **Testing Phase**: 🔄 Pending
   - Test bootstrap on fresh installations
   - Test bootstrap in automated deployment scripts
   - Security audit of bootstrap mechanism
   - Test recovery scenarios
