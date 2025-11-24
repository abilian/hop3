# ADR 008: Web Terminal for Application Management

**Status:** Proposed
**Date:** 2025-01-23
**Deciders:** Development Team
**Tags:** #feature #security #ux

## Context

Users need the ability to access terminal/shell access to their deployed applications directly through the web interface for debugging, troubleshooting, and operational tasks. Currently, users must:
- SSH into the server
- Navigate to the app directory
- Manually set up the environment
- Execute commands

This creates friction and requires SSH access to the host, which may not be desirable in all scenarios.

### Use Cases

1. **Application Debugging:** Execute commands in the app's environment to troubleshoot issues
2. **Database Operations:** Run SQL queries directly in app's database
3. **Log Analysis:** Use grep, tail, and other tools to analyze logs in real-time
4. **File Management:** View, edit, and manage application files
5. **Process Inspection:** Check running processes, resource usage, etc.
6. **Emergency Operations:** Quick access during incidents without SSH setup

### Requirements

**Must Have:**
- Secure, authenticated terminal access per application
- Proper PTY (pseudo-terminal) emulation with colors and control sequences
- Session management with timeouts
- Command execution in app's environment (working directory, env vars)
- Multi-session support (multiple terminal tabs)

**Should Have:**
- Read-only mode for monitoring without command execution
- Session recording for audit and replay
- Copy/paste functionality
- File upload/download capability
- Keyboard shortcuts for power users

**Could Have:**
- Multi-user collaborative terminals
- Database shell integration (psql, mysql client)
- System-level terminal for superadmins
- Command approval workflows for sensitive operations

**Won't Have (v1):**
- Full IDE capabilities
- GUI file editor
- Real-time collaborative editing

## Decision

We will implement a web-based terminal feature using the following architecture:

### Technology Stack

**Frontend:**
- **xterm.js** - Industry-standard terminal emulator
  - Full VT100/xterm terminal emulation
  - Extensive addon ecosystem
  - Excellent performance and compatibility
- **WebSocket** - Real-time bidirectional communication
- **Alpine.js** - Lightweight reactive UI (already in use)

**Backend:**
- **Python PTY module** - Proper terminal emulation with shell
- **Asyncio** - Non-blocking I/O for multiple concurrent sessions
- **Litestar WebSocket routes** - Native framework support
- **Session Manager** - Track and manage active terminal sessions

### Architecture

```
┌─────────────┐
│   Browser   │
│  (xterm.js) │
└──────┬──────┘
       │ WebSocket
       │ /terminal/ws/{session_id}
┌──────▼──────────────────────┐
│  Terminal Controller        │
│  - Authentication           │
│  - Session management       │
│  - Permission checks        │
└──────┬──────────────────────┘
       │
┌──────▼──────────────────────┐
│  Terminal Session Manager   │
│  - Create/destroy sessions  │
│  - Track active sessions    │
│  - Handle timeouts          │
└──────┬──────────────────────┘
       │
┌──────▼──────────────────────┐
│  PTY Process                │
│  - Fork shell in app env    │
│  - Stream stdout/stderr     │
│  - Handle resize, signals   │
└─────────────────────────────┘
```

### Security Model

#### Authentication & Authorization

```python
class TerminalPermission(Enum):
    """Terminal access permissions."""
    APP_TERMINAL = "terminal:app:{app_name}"  # Access specific app terminal
    GLOBAL_TERMINAL = "terminal:global"       # Access any app terminal (admin)
    READONLY_TERMINAL = "terminal:readonly"   # View-only access
```

**Access Control:**
- Only authenticated users can access terminals
- User must have `terminal:app:{app_name}` permission
- Superadmins have `terminal:global` for all apps
- Session-based authentication (no token in URL for security)

#### Command Restrictions

**Configurable Policies:**
```python
# Blacklist mode (default) - block dangerous commands
BLOCKED_COMMANDS = [
    "rm -rf /",
    "dd if=/dev/zero",
    ":(){ :|:& };:",  # fork bomb
]

# Whitelist mode - only allow specific commands (high security)
ALLOWED_COMMANDS = [
    "ls", "cd", "cat", "grep", "tail", "head", "ps", "env"
]

# Confirmation required for destructive operations
CONFIRM_REQUIRED = ["rm", "kill", "shutdown", "reboot"]
```

#### Resource Limits

```python
class TerminalLimits:
    MAX_SESSIONS_PER_USER = 5
    MAX_OUTPUT_BUFFER = 10 * 1024 * 1024  # 10MB
    SESSION_TIMEOUT = 30 * 60  # 30 minutes inactivity
    IDLE_TIMEOUT = 10 * 60  # 10 minutes no I/O
    MAX_CPU_TIME = 300  # 5 minutes per command
    MAX_MEMORY = 512 * 1024 * 1024  # 512MB
```

#### Audit Logging

All terminal sessions will be:
- **Logged:** Start time, end time, user, app, commands executed
- **Recorded:** Full session recording in asciicast v2 format
- **Monitored:** Real-time alerts for suspicious activity

### Implementation Details

#### 1. Terminal Types

**Application Shell (MVP):**
```python
@dataclass
class AppTerminalConfig:
    """Configuration for application terminal."""
    app_name: str
    working_dir: Path  # /home/hop3/apps/{app_name}/src
    shell: str = "/bin/bash"
    env_vars: dict[str, str]  # App's environment
    user: str = "hop3"  # Run as app user
```

**Database Shell (Phase 2):**
```python
@dataclass
class DatabaseTerminalConfig:
    """Configuration for database shell."""
    app_name: str
    service_name: str  # postgres, mysql, redis
    command: str  # psql, mysql, redis-cli
    connection_string: str
    readonly: bool = False
```

**System Shell (Phase 3, Admin only):**
```python
@dataclass
class SystemTerminalConfig:
    """Configuration for system shell."""
    require_2fa: bool = True
    require_approval: bool = True  # Multi-party authorization
    audit_level: str = "verbose"
```

#### 2. WebSocket Protocol

```typescript
// Message types
type TerminalMessage =
  | { type: "input", data: string }           // User input
  | { type: "output", data: string }          // Terminal output
  | { type: "resize", rows: number, cols: number }  // Terminal resize
  | { type: "ping" }                          // Keep-alive
  | { type: "error", message: string }        // Error notification
  | { type: "closed", reason: string }        // Session closed

// Example flow
// Client -> Server
{ type: "input", data: "ls -la\n" }

// Server -> Client
{ type: "output", data: "total 24\ndrwxr-xr-x  5 hop3 hop3 ..." }
{ type: "output", data: "-rw-r--r--  1 hop3 hop3  123 app.py\n" }
```

#### 3. Session Management

```python
class TerminalSession:
    """Represents an active terminal session."""

    session_id: str
    user_id: str
    app_name: str
    pid: int  # PTY process ID
    fd: int  # PTY file descriptor
    created_at: datetime
    last_activity: datetime
    websocket_clients: set[WebSocket]  # Support multiple viewers

    async def start(self, rows: int = 24, cols: int = 80):
        """Fork PTY and start shell."""
        self.pid, self.fd = pty.fork()

        if self.pid == 0:  # Child
            os.chdir(f"/home/hop3/apps/{self.app_name}/src")
            os.execvpe("/bin/bash", ["/bin/bash"], self.env_vars)

        # Parent - set terminal size
        self.resize(rows, cols)

    async def write(self, data: bytes):
        """Write input to terminal."""
        os.write(self.fd, data)
        self.last_activity = datetime.now(UTC)

    async def read(self) -> bytes:
        """Read output from terminal."""
        return os.read(self.fd, 4096)
```

#### 4. Frontend Integration

```javascript
// Initialize xterm.js
import { Terminal } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import { WebLinksAddon } from 'xterm-addon-web-links';

const terminal = new Terminal({
  cursorBlink: true,
  fontSize: 14,
  fontFamily: 'Menlo, Monaco, "Courier New", monospace',
  theme: {
    background: '#1e1e1e',
    foreground: '#d4d4d4',
  },
  scrollback: 10000,
});

const fitAddon = new FitAddon();
terminal.loadAddon(fitAddon);
terminal.loadAddon(new WebLinksAddon());

// Connect WebSocket
const ws = new WebSocket(`wss://${location.host}/terminal/ws/${sessionId}`);

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  if (msg.type === 'output') {
    terminal.write(msg.data);
  }
};

terminal.onData((data) => {
  ws.send(JSON.stringify({ type: 'input', data }));
});
```

### UI/UX Design

#### Dashboard Integration

**App Detail Page:**
```
┌─────────────────────────────────────────────┐
│ App: myapp                    [Terminal]    │
├─────────────────────────────────────────────┤
│ Status: RUNNING | Logs | Env | Settings    │
└─────────────────────────────────────────────┘
```

**Terminal Page:**
```
┌─────────────────────────────────────────────────────┐
│ Terminal: myapp                                      │
├─────────────────────────────────────────────────────┤
│ [Session 1] [Session 2] [+ New]  [⬇ Download] [×]  │
├─────────────────────────────────────────────────────┤
│                                                     │
│  hop3@myapp:~/apps/myapp/src$ ls -la              │
│  total 24                                          │
│  drwxr-xr-x 5 hop3 hop3 4096 Jan 23 10:00 .       │
│  drwxr-xr-x 3 hop3 hop3 4096 Jan 23 09:00 ..      │
│  -rw-r--r-- 1 hop3 hop3  123 Jan 23 10:00 app.py  │
│  hop3@myapp:~/apps/myapp/src$ _                    │
│                                                     │
├─────────────────────────────────────────────────────┤
│ Connected | Idle: 0m | Ctrl+Shift+C/V | Settings   │
└─────────────────────────────────────────────────────┘
```

**Keyboard Shortcuts:**
- `Ctrl+Shift+T` - New terminal session
- `Ctrl+Shift+W` - Close current session
- `Ctrl+Shift+C` - Copy selection
- `Ctrl+Shift+V` - Paste from clipboard
- `Ctrl+Shift+F` - Search in terminal

### Configuration

```toml
# hop3.toml
[terminal]
enabled = true
max_sessions_per_user = 5
session_timeout = 1800  # 30 minutes
idle_timeout = 600  # 10 minutes

[terminal.security]
# Command filtering
command_filtering_mode = "blacklist"  # "blacklist", "whitelist", or "none"
blocked_commands = ["rm -rf /", "dd if=/dev/zero"]
require_confirmation = ["rm", "kill", "shutdown"]

# Recording and audit
record_all_sessions = true
audit_log_path = "/var/log/hop3/terminal-audit.log"

# System terminal (superadmin only)
require_2fa_for_system_terminal = true

[terminal.limits]
max_output_buffer = 10485760  # 10MB
max_cpu_time = 300  # 5 minutes
max_memory = 536870912  # 512MB
```

## Implementation Phases

### Phase 1: MVP (Weeks 1-2)
**Goal:** Basic terminal functionality for applications

- [ ] Terminal session management (create, destroy, timeout)
- [ ] PTY-backed shell execution
- [ ] WebSocket communication
- [ ] Basic xterm.js UI
- [ ] Authentication and app-scoped permissions
- [ ] Single session per user
- [ ] Basic command execution (no filtering yet)

**Deliverables:**
- Working terminal accessible from app detail page
- Users can execute commands in their app's environment
- Sessions auto-close after timeout
- Basic audit logging

### Phase 2: Enhanced Features (Weeks 3-4)
**Goal:** Production-ready with security and UX improvements

- [ ] Multiple sessions per user (tabs)
- [ ] Command filtering (blacklist/whitelist)
- [ ] Session recording (asciicast format)
- [ ] Copy/paste support
- [ ] Terminal search
- [ ] Resource limits enforcement
- [ ] Read-only mode
- [ ] Better error handling and user feedback

**Deliverables:**
- Multi-tab terminal interface
- Session recordings can be viewed/downloaded
- Command filtering prevents dangerous operations
- Users can copy/paste with clipboard integration

### Phase 3: Advanced Features (Weeks 5-6)
**Goal:** Power-user features

- [ ] File upload/download through terminal
- [ ] Database shell integration (psql, mysql)
- [ ] Terminal history and search across sessions
- [ ] Collaborative terminals (multi-user view/control)
- [ ] System terminal for superadmins
- [ ] Session sharing (read-only links)

**Deliverables:**
- Users can upload/download files via terminal
- Direct database access through web terminal
- Admins can share terminal sessions with team
- System-level terminal for infrastructure management

### Phase 4: Enterprise (Future)
**Goal:** Compliance and enterprise features

- [ ] Multi-party authorization for sensitive commands
- [ ] Integration with external audit systems
- [ ] RBAC with granular command permissions
- [ ] Command approval workflows
- [ ] SSO/SAML integration
- [ ] Session replay with timeline scrubbing

## Consequences

### Positive

**For Users:**
- ✅ Faster debugging and troubleshooting
- ✅ No need for SSH access to server
- ✅ Accessible from any device with browser
- ✅ Session history and recordings for future reference
- ✅ Safer than giving full SSH access

**For Operations:**
- ✅ Complete audit trail of all terminal activity
- ✅ Ability to restrict dangerous commands
- ✅ Resource limits prevent runaway processes
- ✅ Session recordings aid in training and incident response
- ✅ Fine-grained access control (app-specific terminals)

**For Platform:**
- ✅ Feature parity with Heroku, Render, Railway
- ✅ Differentiator from simpler PaaS offerings
- ✅ Reduces support burden (users can self-diagnose)
- ✅ Enables power users to do advanced operations

### Negative

**Security Risks:**
- ⚠️ New attack surface (WebSocket endpoint)
- ⚠️ Risk of privilege escalation if not implemented carefully
- ⚠️ Command injection if input not properly sanitized
- ⚠️ Resource exhaustion (fork bombs, infinite loops)
- ⚠️ Session hijacking if WebSocket not properly secured

**Mitigation:**
- Use session-based auth (no tokens in URLs)
- Implement command filtering and confirmation
- Enforce strict resource limits (CPU, memory, time)
- Regular security audits and penetration testing
- Rate limiting on WebSocket connections

**Performance Concerns:**
- ⚠️ Each terminal session requires a PTY (file descriptor)
- ⚠️ WebSocket connections are long-lived
- ⚠️ Large output can overwhelm browser/network
- ⚠️ Session recordings can grow large

**Mitigation:**
- Limit sessions per user (5 default)
- Output buffer size limits (10MB default)
- Automatic session cleanup on idle timeout
- Compress recordings with gzip
- Optional: store recordings in S3/object storage

**Complexity:**
- ⚠️ PTY management is complex (signals, resize, terminal modes)
- ⚠️ WebSocket state management
- ⚠️ Multi-session coordination
- ⚠️ Browser compatibility issues with xterm.js

**Mitigation:**
- Use battle-tested libraries (xterm.js, Python pty module)
- Comprehensive testing (unit, integration, E2E)
- Progressive enhancement (graceful degradation)
- Clear documentation and troubleshooting guides

## Alternatives Considered

### 1. SSH-based Terminal (Wetty/ttyd)

**Pros:**
- Leverage existing SSH infrastructure
- Standard protocol, well-tested
- No new server-side code

**Cons:**
- Requires SSH access to server
- Harder to implement fine-grained permissions
- No easy way to restrict to app environment
- Session recording more difficult

**Decision:** ❌ Rejected - Need app-scoped access without SSH

### 2. Execute via RPC (Current Approach)

**Pros:**
- Already have RPC infrastructure
- Simple request/response model

**Cons:**
- No interactive shell (no PTY)
- No real-time output streaming
- Can't use interactive tools (vim, top, etc.)
- Poor user experience

**Decision:** ❌ Not sufficient - Need proper terminal

### 3. Container Exec (Docker/Podman)

**Pros:**
- Native container isolation
- Standard exec interface

**Cons:**
- Requires containerization (not all apps use containers)
- More complex infrastructure
- Harder to implement resource limits

**Decision:** ❌ Not applicable - Not container-based yet

### 4. Gotty/Tmate (Standalone Terminal Sharing)

**Pros:**
- Off-the-shelf solution
- Minimal integration needed

**Cons:**
- External dependency
- Limited customization
- No integration with our auth system
- Can't enforce app-scoped permissions

**Decision:** ❌ Rejected - Need tight integration

## References

### Similar Implementations

1. **Heroku Exec** - Terminal access via SSH tunnel
2. **Railway.app** - Web terminal per service
3. **Render.com** - Shell access in dashboard
4. **AWS Cloud9** - Full IDE with integrated terminal
5. **Google Cloud Shell** - Web-based terminal for GCP

### Libraries & Tools

**Frontend:**
- [xterm.js](https://xtermjs.org/) - Terminal emulator
- [local-echo](https://github.com/wavesoft/local-echo) - Input handling

**Backend:**
- [pty (Python)](https://docs.python.org/3/library/pty.html) - Pseudo-terminal utilities
- [pyte](https://github.com/selectel/pyte) - Terminal emulator (if needed)

**Recording:**
- [asciinema](https://asciinema.org/) - Terminal session recording format

### Security Standards

- [OWASP - Command Injection Prevention](https://cheatsheetseries.owasp.org/cheatsheets/OS_Command_Injection_Defense_Cheat_Sheet.html)
- [CWE-78: OS Command Injection](https://cwe.mitre.org/data/definitions/78.html)
- [CWE-77: Command Injection](https://cwe.mitre.org/data/definitions/77.html)

## Open Questions

1. **Should we support system-level terminals for superadmins?**
   - Pros: Full control, emergency access
   - Cons: High risk, requires 2FA and audit
   - Recommendation: Phase 3, with strict controls

2. **How should we handle terminal recording storage?**
   - Option A: Local file system (simple, limited space)
   - Option B: Object storage (S3/MinIO) (scalable, more complex)
   - Recommendation: Start with local, add S3 in Phase 4

3. **Should terminals be isolated in separate processes/containers?**
   - Pros: Better isolation, resource control
   - Cons: More complex, requires containerization
   - Recommendation: Use PTY with resource limits (Phase 1), consider containers later

4. **How to handle collaborative terminals (multiple users)?**
   - Option A: One person controls, others view
   - Option B: All can control (race conditions possible)
   - Option C: Token-based control passing
   - Recommendation: Option A (Phase 3), Option C for advanced use

5. **Should we support terminal themes/customization?**
   - Pros: Better UX, accessibility
   - Cons: Additional complexity
   - Recommendation: Phase 2 (basic themes), Phase 4 (full customization)

## Success Metrics

**Adoption:**
- 50% of active users try terminal in first month
- 25% of active users use terminal weekly

**Performance:**
- Terminal connects in < 500ms
- Output latency < 100ms (P95)
- Zero security incidents related to terminal

**User Satisfaction:**
- Terminal feature rated 4+ stars
- < 5% of support tickets mention terminal issues

## Next Steps

1. **Create detailed implementation plan** for Phase 1
2. **Security review** with team before implementation
3. **Prototype** basic terminal with xterm.js + WebSocket
4. **User testing** with 5-10 beta users
5. **Documentation** (user guide, admin guide, security guide)
6. **Gradual rollout** (beta → production)
