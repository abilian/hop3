# ADR 023: Authentication Bootstrap Process

**Status**: Draft (Early)

## Context and Goals

Hop3 uses JWT-based bearer token authentication for API access. The current authentication flow requires users to:

1. Register an account (`hop3 auth:register`)
2. Login to receive a JWT token (`hop3 auth:login`)
3. Store the token in `~/.config/hop3-cli/config.toml`
4. Include the token in subsequent requests via `Authorization: Bearer <token>` header

However, there is a bootstrap problem: **How do we create the first admin user and obtain the initial authentication token?**

While `auth:register` and `auth:login` are marked as public commands (no authentication required), there is no documented process for:
- Creating the initial admin user on a fresh Hop3 installation
- Generating an initial token without requiring a pre-existing user
- Securing the server while allowing initial setup

This creates friction in deployment scenarios where:
- A server is provisioned and needs an admin account
- Automated deployment scripts need to bootstrap authentication
- Multiple administrators need to be onboarded securely

## Decision

*To be determined - this is an early draft documenting the problem and potential solutions.*

## Proposed Solutions

### Option 1: Server-side CLI Command (Recommended)

Create a dedicated server-side command for creating admin users:

```bash
hop-server user:create-admin <username> <email> <password>
```

**How it works:**
- Runs directly on the server (via SSH or local access)
- Creates user in database with `is_admin=True`
- Generates and displays JWT token for immediate use
- Can be used for initial bootstrap and subsequent admin creation

**Characteristics:**
- Explicit and auditable
- Requires server access (SSH or local)
- Works with existing architecture
- Can generate tokens for existing users too

### Option 2: Bootstrap Token in Environment

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

### Option 3: Database Migration with Seed User

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

### Option 4: Conditional Public Registration

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

## Comparison Matrix

| Criteria | Option 1: CLI | Option 2: Bootstrap Token | Option 3: Seed User | Option 4: Conditional |
|----------|---------------|---------------------------|---------------------|-----------------------|
| Security | ✅ High | ⚠️ Medium | ❌ Low | ⚠️ Medium |
| Automation | ⚠️ Requires SSH | ✅ Fully automated | ✅ Fully automated | ⚠️ Requires coordination |
| Auditability | ✅ Explicit | ✅ Token generation logged | ⚠️ Default credentials | ❌ Implicit |
| User Experience | ⚠️ Requires server access | ✅ Seamless | ✅ Simple | ✅ Self-service |
| Implementation | ✅ Simple | ⚠️ Token management | ✅ Simple | ⚠️ Race conditions |

## Consequences

### Benefits (General)

- **Clear Bootstrap Process**: Documented path from fresh installation to authenticated operations
- **Automation Support**: Enables CI/CD pipelines and infrastructure-as-code deployments
- **Security Boundary**: Explicit separation between bootstrap and normal operations
- **Admin Onboarding**: Standardized process for creating additional administrators

### Drawbacks (General)

- **Added Complexity**: Additional mechanism beyond normal authentication flow
- **Documentation Burden**: Must be clearly documented to avoid confusion
- **Security Considerations**: Bootstrap mechanism is inherently privileged and requires careful design

### Option-Specific Trade-offs

**Option 1 (CLI Command)**:
- ✅ Most secure - requires server access
- ❌ Less convenient - requires SSH for remote servers
- ✅ Most explicit - clear audit trail

**Option 2 (Bootstrap Token)**:
- ✅ Automation-friendly
- ❌ Token management complexity
- ⚠️ Shared secret security concerns

**Option 3 (Seed User)**:
- ✅ Simplest implementation
- ❌ Well-known credentials security risk
- ⚠️ Requires forced password change

**Option 4 (Conditional)**:
- ✅ Self-service
- ❌ Race condition risks
- ⚠️ Network isolation requirements

## Risks

### Security Risks

- **Privilege Escalation**: Bootstrap mechanism provides elevated privileges that could be abused if not properly secured
- **Credential Exposure**: Default credentials or bootstrap tokens could be leaked or discovered
- **Race Conditions**: Multiple simultaneous bootstrap attempts could create security vulnerabilities

**Mitigation**:
- Implement bootstrap mechanism with time limits or usage counts
- Require immediate password/token rotation after bootstrap
- Log all bootstrap operations for audit
- Consider requiring confirmation step for bootstrap operations

### Operational Risks

- **Locked Out Admin**: If bootstrap process fails, admin may be locked out
- **Token Loss**: If initial token is lost before being saved, recovery process needed
- **Documentation Gap**: Users may not find or follow bootstrap instructions

**Mitigation**:
- Provide multiple recovery mechanisms
- Clear error messages with recovery instructions
- Comprehensive documentation with examples

## Action Items

1. **Decision Phase**:
   - Review proposed options with team
   - Evaluate security implications of each approach
   - Consider deployment scenarios (bare metal, containers, cloud)
   - Select preferred option or hybrid approach

2. **Design Phase**:
   - Document detailed authentication flow with bootstrap
   - Design API/CLI interface for chosen option
   - Plan security measures (token rotation, audit logging)
   - Define error handling and recovery procedures

3. **Implementation Phase**:
   - Implement server-side bootstrap mechanism
   - Add CLI commands for bootstrap operations
   - Implement audit logging for bootstrap events
   - Add tests for bootstrap scenarios

4. **Documentation Phase**:
   - Update installation guide with bootstrap instructions
   - Document security best practices
   - Provide examples for common deployment scenarios
   - Create troubleshooting guide for bootstrap issues

5. **Testing Phase**:
   - Test bootstrap on fresh installations
   - Test bootstrap in automated deployment scripts
   - Security audit of bootstrap mechanism
   - Test recovery scenarios

## References

- Current authentication code: `packages/hop3-server/src/hop3/server/middleware/auth.py`
- Token management: `packages/hop3-server/src/hop3/server/security/tokens.py`
- Auth commands: `packages/hop3-server/src/hop3/commands/auth.py`
- RPC public commands: `packages/hop3-server/src/hop3/server/views/rpc.py`

## Related ADRs

- ADR 020: Security and Resilience Enhancements
- ADR 022: Multi-Factor Authentication (MFA)
